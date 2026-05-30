import tempfile
import unittest
from pathlib import Path

from app.library.streaming import (
    InvalidLibraryPath,
    RangeNotSatisfiable,
    iter_file_range,
    parse_range_header,
    resolve_library_file,
)


class StreamingTests(unittest.TestCase):
    def test_parse_regular_range(self):
        spec = parse_range_header("bytes=10-19", 100)
        self.assertEqual(spec.start, 10)
        self.assertEqual(spec.end, 19)
        self.assertEqual(spec.length, 10)
        self.assertEqual(spec.content_range, "bytes 10-19/100")

    def test_parse_suffix_range(self):
        spec = parse_range_header("bytes=-10", 100)
        self.assertEqual(spec.start, 90)
        self.assertEqual(spec.end, 99)

    def test_invalid_range_raises(self):
        with self.assertRaises(RangeNotSatisfiable):
            parse_range_header("bytes=100-120", 100)

    def test_iter_file_range(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "track.mp3"
            path.write_bytes(b"0123456789")
            data = b"".join(iter_file_range(path, 2, 5, chunk_size=2))
            self.assertEqual(data, b"2345")

    def test_resolve_library_file_accepts_nested_storage_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "library"
            root.mkdir()

            path = resolve_library_file(root, "album/track.mp3")

            self.assertEqual(path, (root / "album" / "track.mp3").resolve())

    def test_resolve_library_file_rejects_parent_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "library"
            root.mkdir()

            with self.assertRaises(InvalidLibraryPath):
                resolve_library_file(root, "../outside.mp3")

    def test_resolve_library_file_rejects_similar_prefix_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "library"
            sibling = Path(tmp) / "library-other"
            root.mkdir()
            sibling.mkdir()

            with self.assertRaises(InvalidLibraryPath):
                resolve_library_file(root, "../library-other/track.mp3")


if __name__ == "__main__":
    unittest.main()
