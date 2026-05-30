from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


class RangeNotSatisfiable(ValueError):
    pass


class InvalidLibraryPath(ValueError):
    pass


@dataclass(frozen=True)
class RangeSpec:
    start: int
    end: int
    size: int

    @property
    def length(self) -> int:
        return self.end - self.start + 1

    @property
    def content_range(self) -> str:
        return f"bytes {self.start}-{self.end}/{self.size}"


def parse_range_header(header: str, size: int) -> RangeSpec:
    if size <= 0:
        raise RangeNotSatisfiable("Cannot stream an empty file.")
    if not header.startswith("bytes="):
        raise RangeNotSatisfiable("Only bytes ranges are supported.")
    range_value = header.removeprefix("bytes=").strip()
    if "," in range_value:
        raise RangeNotSatisfiable("Multiple ranges are not supported.")
    start_text, sep, end_text = range_value.partition("-")
    if sep != "-":
        raise RangeNotSatisfiable("Invalid range header.")

    if start_text == "":
        suffix_length = _parse_int(end_text)
        if suffix_length <= 0:
            raise RangeNotSatisfiable("Invalid suffix range.")
        start = max(0, size - suffix_length)
        end = size - 1
    else:
        start = _parse_int(start_text)
        end = _parse_int(end_text) if end_text else size - 1

    if start < 0 or end < start or start >= size:
        raise RangeNotSatisfiable("Requested range is outside the file.")
    end = min(end, size - 1)
    return RangeSpec(start=start, end=end, size=size)


def iter_file_range(path: Path, start: int, end: int, chunk_size: int = 1024 * 1024):
    remaining = end - start + 1
    with path.open("rb") as audio:
        audio.seek(start)
        while remaining > 0:
            chunk = audio.read(min(chunk_size, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


def resolve_library_file(library_root: Path, storage_key: str) -> Path:
    root = library_root.expanduser().resolve()
    path = (root / storage_key).resolve()
    if path == root or root not in path.parents:
        raise InvalidLibraryPath("Audio path escaped the library root.")
    return path


def _parse_int(value: str) -> int:
    try:
        return int(value)
    except ValueError as exc:
        raise RangeNotSatisfiable("Invalid byte range value.") from exc
