import pytest

from app.catalog import bencode


def test_decode_integer():
    assert bencode.decode(b"i42e") == 42


def test_decode_negative_integer():
    assert bencode.decode(b"i-7e") == -7


def test_decode_string():
    assert bencode.decode(b"4:spam") == b"spam"


def test_decode_list():
    assert bencode.decode(b"l4:spam4:eggse") == [b"spam", b"eggs"]


def test_decode_dict():
    assert bencode.decode(b"d3:cow3:moo4:spam4:eggse") == {b"cow": b"moo", b"spam": b"eggs"}


def test_decode_nested_torrent_like_structure():
    data = (
        b"d4:infod4:name8:test.mp35:filesl"
        b"d4:pathl3:dir8:file.mp3e6:lengthi1000eee"
        b"ee"
    )
    decoded = bencode.decode(data)
    info = decoded[b"info"]
    assert info[b"name"] == b"test.mp3"
    assert info[b"files"][0][b"path"] == [b"dir", b"file.mp3"]
    assert info[b"files"][0][b"length"] == 1000


def test_decode_trailing_data_raises():
    with pytest.raises(bencode.BencodeError):
        bencode.decode(b"i1eextra")


def test_decode_malformed_raises():
    with pytest.raises(bencode.BencodeError):
        bencode.decode(b"x")
