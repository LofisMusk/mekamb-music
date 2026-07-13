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


class TestMonitoredReleaseId:
    def test_prefers_monitored_release(self):
        assert ia_import.monitored_release_id({"releases": [{"id": 1, "monitored": False}, {"id": 2, "monitored": True}]}) == 2

    def test_falls_back_to_first_release(self):
        assert ia_import.monitored_release_id({"releases": [{"id": 5, "monitored": False}]}) == 5

    def test_none_when_no_releases(self):
        assert ia_import.monitored_release_id({"releases": []}) is None


class TestMapFilesToTracks:
    def _q(self):
        return {"quality": {"id": 8, "name": "MP3-320"}}

    def test_maps_by_filename_track_number_tolerating_gaps(self):
        # 26 files for a 27-track release: file "20 ..." lands on track 20 even
        # though track (say) 8 has no file — mirrors the real 1-800 case.
        tracks = [{"id": 3500 + n, "trackNumber": str(n), "mediumNumber": 1} for n in range(1, 28)]
        pairs = [("/a/01 Intro.mp3", self._q()), ("/a/20 #8 - Kacik.mp3", self._q())]
        mapped = ia_import.map_files_to_tracks(pairs, tracks)
        assert [(p, tid) for p, _, tid in mapped] == [("/a/01 Intro.mp3", 3501), ("/a/20 #8 - Kacik.mp3", 3520)]

    def test_falls_back_to_positional_when_filenames_unnumbered(self):
        tracks = [{"id": 11, "trackNumber": "1", "mediumNumber": 1}, {"id": 12, "trackNumber": "2", "mediumNumber": 1}]
        pairs = [("/a/Bakayoko.mp3", self._q()), ("/a/Anja.mp3", self._q())]
        mapped = ia_import.map_files_to_tracks(pairs, tracks)
        # sorted by path: Anja -> track 1, Bakayoko -> track 2
        assert [(p, tid) for p, _, tid in mapped] == [("/a/Anja.mp3", 11), ("/a/Bakayoko.mp3", 12)]

    def test_drops_files_without_quality(self):
        assert ia_import.map_files_to_tracks([("/a/01.mp3", None)], [{"id": 1, "trackNumber": "1"}]) == []


class TestBuildManualImportFiles:
    def test_forces_target_ids_and_track_mapping(self):
        tracks = [{"id": 3584, "trackNumber": "1", "mediumNumber": 1}, {"id": 3586, "trackNumber": "3", "mediumNumber": 1}]
        pairs = [("/d/01 - Marmur.mp3", {"quality": {"name": "MP3-320"}}), ("/d/03 - Zyrandol.mp3", {"quality": {"name": "MP3-320"}})]
        files = ia_import.build_manual_import_files(pairs, tracks, artist_id=5, album_id=34, album_release_id=211)
        assert [f["trackIds"] for f in files] == [[3584], [3586]]
        assert all(f["albumId"] == 34 and f["artistId"] == 5 and f["albumReleaseId"] == 211 for f in files)
        assert all(f["disableReleaseSwitching"] for f in files)

    def test_empty_when_no_tracks(self):
        pairs = [("/d/01.mp3", {"quality": {"name": "MP3-320"}})]
        assert ia_import.build_manual_import_files(pairs, [], artist_id=1, album_id=1, album_release_id=1) == []


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
