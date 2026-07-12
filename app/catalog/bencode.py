from __future__ import annotations

BencodeValue = int | bytes | list["BencodeValue"] | dict[bytes, "BencodeValue"]


class BencodeError(ValueError):
    pass


def decode(data: bytes) -> BencodeValue:
    """Minimal bencode decoder — just enough to read a .torrent file's `info`
    dict (name, files/length). No encoder; we only ever consume .torrent files
    that archive.org already produced."""
    value, offset = _decode(data, 0)
    if offset != len(data):
        raise BencodeError("trailing data after top-level value")
    return value


def _decode(data: bytes, offset: int) -> tuple[BencodeValue, int]:
    if offset >= len(data):
        raise BencodeError("unexpected end of data")
    marker = data[offset : offset + 1]
    if marker == b"i":
        return _decode_int(data, offset)
    if marker == b"l":
        return _decode_list(data, offset)
    if marker == b"d":
        return _decode_dict(data, offset)
    if marker.isdigit():
        return _decode_string(data, offset)
    raise BencodeError(f"unexpected token {marker!r} at offset {offset}")


def _decode_int(data: bytes, offset: int) -> tuple[int, int]:
    end = data.index(b"e", offset)
    return int(data[offset + 1 : end]), end + 1


def _decode_string(data: bytes, offset: int) -> tuple[bytes, int]:
    colon = data.index(b":", offset)
    length = int(data[offset:colon])
    start = colon + 1
    end = start + length
    return data[start:end], end


def _decode_list(data: bytes, offset: int) -> tuple[list[BencodeValue], int]:
    items: list[BencodeValue] = []
    offset += 1
    while data[offset : offset + 1] != b"e":
        item, offset = _decode(data, offset)
        items.append(item)
    return items, offset + 1


def _decode_dict(data: bytes, offset: int) -> tuple[dict[bytes, BencodeValue], int]:
    result: dict[bytes, BencodeValue] = {}
    offset += 1
    while data[offset : offset + 1] != b"e":
        key, offset = _decode_string(data, offset)
        value, offset = _decode(data, offset)
        result[key] = value
    return result, offset + 1
