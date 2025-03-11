import array

import pytest
from acoustid_ext.fingerprint import decode_fingerprint, encode_fingerprint


def test_encode_fingerprint_list() -> None:
    data = encode_fingerprint([1, 2, 3], 99)

    assert data[0:2] == b"Fp"
    assert data[2] == 1
    assert data[3] == 99

    assert int.from_bytes(data[4:8], byteorder="little") == 1
    assert int.from_bytes(data[8:12], byteorder="little") == 2 ^ 1
    assert int.from_bytes(data[12:16], byteorder="little") == 3 ^ 2

    assert len(data) == 4 + 4 * 3


def test_encode_fingerprint_list_invalid_type() -> None:
    with pytest.raises(TypeError):
        encode_fingerprint(["1", "2", "3"], 99)  # type: ignore


def test_encode_fingerprint_array() -> None:
    data = encode_fingerprint(array.array("I", [1, 2, 3]), 99)

    assert data[0:2] == b"Fp"
    assert data[2] == 1
    assert data[3] == 99

    assert int.from_bytes(data[4:8], byteorder="little") == 1
    assert int.from_bytes(data[8:12], byteorder="little") == 2 ^ 1
    assert int.from_bytes(data[12:16], byteorder="little") == 3 ^ 2

    assert len(data) == 4 + 4 * 3


def test_encode_fingerprint_array_invalid_type() -> None:
    with pytest.raises(TypeError):
        encode_fingerprint(array.array("h", [1, 2, 3]), 99)


def test_decode_fingerprint() -> None:
    data = encode_fingerprint([1, 2, 3], 99)
    hashes, version = decode_fingerprint(data)
    assert hashes == array.array("L", [1, 2, 3])
    assert version == 99
