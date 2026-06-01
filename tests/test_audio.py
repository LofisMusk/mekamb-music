import tempfile
import unittest
from pathlib import Path

from app.library.audio import is_allowed_audio_file, media_type_for_audio_file, scan_audio_file


class AudioTests(unittest.TestCase):
    def test_allowed_audio_extensions(self):
        with tempfile.TemporaryDirectory() as tmp:
            flac = Path(tmp) / "track.flac"
            txt = Path(tmp) / "notes.txt"
            flac.write_bytes(b"not real flac but extension is allowed for quarantine filtering")
            txt.write_text("nope")

            self.assertTrue(is_allowed_audio_file(flac))
            self.assertFalse(is_allowed_audio_file(txt))

    def test_scan_uses_original_quality_extension_as_codec_hint(self):
        with tempfile.TemporaryDirectory() as tmp:
            mp3 = Path(tmp) / "track.mp3"
            mp3.write_bytes(b"fake")

            metadata = scan_audio_file(mp3)

            self.assertEqual(metadata.title, "track")
            self.assertEqual(metadata.codec, "mp3")
            self.assertEqual(metadata.size_bytes, 4)

    def test_media_type_uses_audio_extension_map(self):
        self.assertEqual(media_type_for_audio_file(Path("track.flac")), "audio/flac")
        self.assertEqual(media_type_for_audio_file(Path("track.mp3")), "audio/mpeg")


if __name__ == "__main__":
    unittest.main()
