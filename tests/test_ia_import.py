from app.catalog import ia_import


class TestScoreCandidate:
    def test_exact_artist_and_album_scores_highest(self):
        score = ia_import.score_candidate(
            "Taco Hemingway", "Marmur", "Taco Hemingway – Marmur (MP3)", "taco-hemingway-marmur_202405"
        )
        assert score == 1.0

    def test_strips_polish_diacritics_and_format_noise(self):
        # "1-800-OŚWIECENIE" vs an item titled with ascii "OSWIECENIE [MP3]"
        score = ia_import.score_candidate(
            "Taco Hemingway", "1-800-OŚWIECENIE", "Taco Hemingway - 1 800 Oswiecenie [MP3]"
        )
        assert score == 1.0

    def test_unicode_hyphen_title_matches_ascii_hyphen_item(self):
        # Album title uses U+2010 hyphens ("1‐800‐OŚWIECENIE"); the archive.org
        # item uses ASCII hyphens. Regression: the folded token must split on the
        # unicode hyphen, not glue into one "1800oswiecenie" token.
        score = ia_import.score_candidate(
            "Taco Hemingway",
            "1‐800‐OŚWIECENIE",
            "Taco Hemingway – 1-800-OŚWIECENIE (MP3)",
            "taco-hemingway-1-800-oswiecenie",
        )
        assert score == 1.0

    def test_artistless_identifier_still_matches_on_album(self):
        # "tacohem-marmur-2016" has no parseable artist token but the album lands.
        score = ia_import.score_candidate("Taco Hemingway", "Marmur", "tacohem-marmur-2016")
        assert 0.6 <= score < 1.0

    def test_wrong_album_by_same_artist_scores_zero(self):
        assert ia_import.score_candidate("Taco Hemingway", "Marmur", "Taco Hemingway - Europa") == 0.0

    def test_empty_album_scores_zero(self):
        assert ia_import.score_candidate("Taco Hemingway", "", "anything") == 0.0


class TestRankCandidates:
    def test_real_release_outranks_noise(self):
        docs = [
            {"identifier": "youtube-x", "title": "ILC Gala: Dr. Eli Marmur praised", "downloads": 9},
            {"identifier": "taco-hemingway-marmur_202405", "title": "Taco Hemingway – Marmur (MP3)", "downloads": 300},
            {"identifier": "gov.uscourts.nysd.650731", "title": "Teman v. Marmur", "downloads": 1},
        ]
        ranked = ia_import.rank_candidates("Taco Hemingway", "Marmur", docs)
        assert ranked[0].identifier == "taco-hemingway-marmur_202405"
        assert ranked[0].score == 1.0

    def test_drops_non_matches(self):
        docs = [{"identifier": "thingiverse-5549008", "title": "Marmur Filament Swatch"}]
        # album token present but this is scored by album+artist; artist absent → 0.7,
        # still a (weak) match on this single-word album, so it is *not* silently
        # dropped — the min-score gate in the worker is what filters it.
        ranked = ia_import.rank_candidates("Taco Hemingway", "Marmur", docs)
        assert all(c.score > 0 for c in ranked)

    def test_skips_docs_without_identifier(self):
        ranked = ia_import.rank_candidates("A", "Marmur", [{"title": "Marmur"}])
        assert ranked == []


class TestBuildManualImportFiles:
    def _candidate(self, path, track_ids, *, release_id=211, rejections=None):
        return {
            "path": path,
            "quality": {"quality": {"id": 8, "name": "MP3-VBR-V0"}, "revision": {"version": 1}},
            "albumReleaseId": release_id,
            "tracks": [{"id": tid} for tid in track_ids],
            "rejections": rejections or [],
        }

    def test_reshapes_lidarr_candidates_forcing_target_ids(self):
        # Shape mirrors the real prod manualimport response validated against Lidarr.
        candidates = [
            self._candidate("/data/ia/01 - Marmur.mp3", [3584]),
            self._candidate("/data/ia/03 - Żyrandol.mp3", [3586]),
        ]
        files = ia_import.build_manual_import_files(candidates, artist_id=5, album_id=34)
        assert [f["path"] for f in files] == [
            "/data/ia/01 - Marmur.mp3",
            "/data/ia/03 - Żyrandol.mp3",
        ]
        assert [f["trackIds"] for f in files] == [[3584], [3586]]
        assert all(f["albumId"] == 34 and f["artistId"] == 5 and f["albumReleaseId"] == 211 for f in files)

    def test_skips_files_lidarr_could_not_map_to_a_track(self):
        candidates = [self._candidate("/a/junk.mp3", [])]
        assert ia_import.build_manual_import_files(candidates, artist_id=1, album_id=1) == []

    def test_skips_files_without_quality_or_release(self):
        candidates = [
            {"path": "/a/x.mp3", "quality": None, "albumReleaseId": 1, "tracks": [{"id": 1}]},
            {"path": "/a/y.mp3", "quality": {"quality": {}}, "albumReleaseId": None, "tracks": [{"id": 2}]},
        ]
        assert ia_import.build_manual_import_files(candidates, artist_id=1, album_id=1) == []

    def test_skips_permanently_rejected_files(self):
        candidates = [
            self._candidate("/a/dupe.mp3", [1], rejections=[{"reason": "existing", "type": "permanent"}]),
            self._candidate("/a/ok.mp3", [2], rejections=[{"reason": "note", "type": "warning"}]),
        ]
        files = ia_import.build_manual_import_files(candidates, artist_id=1, album_id=1)
        assert [f["path"] for f in files] == ["/a/ok.mp3"]  # warning kept, permanent dropped


class TestSelectAudioFormat:
    def test_prefers_mp3_over_lossless(self):
        assert ia_import.select_audio_format(["PNG", "Flac", "VBR MP3", "Spectrogram"]) == "VBR MP3"

    def test_falls_back_to_lossless_when_no_mp3(self):
        assert ia_import.select_audio_format(["PNG", "Flac", "Metadata"]) == "Flac"

    def test_none_when_no_audio_format(self):
        assert ia_import.select_audio_format(["PNG", "Spectrogram", "Metadata"]) is None

    def test_picks_higher_bitrate_mp3_first(self):
        assert ia_import.select_audio_format(["128Kbps MP3", "320Kbps MP3"]) == "320Kbps MP3"


class TestStagingFolderName:
    def test_builds_artist_album_name(self):
        assert ia_import.staging_folder_name("Taco Hemingway", "Marmur") == "Taco Hemingway - Marmur"

    def test_sanitizes_path_separators(self):
        assert "/" not in ia_import.staging_folder_name("AC/DC", "Back/Slash")
