import array

import pytest
from acoustid_ext.fingerprint import (
    compute_shingled_simhashes,
    compute_simhash,
    decode_fingerprint,
    encode_fingerprint,
)

from tests import (
    TEST_1A_FP_RAW,
    TEST_1B_FP_RAW,
    TEST_1C_FP_RAW,
    TEST_1D_FP_RAW,
    TEST_2_FP_RAW,
)


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


def test_decode_fingerprint_namedtuple() -> None:
    data = encode_fingerprint([1, 2, 3], 99)
    fp = decode_fingerprint(data)
    assert fp.hashes == array.array("L", [1, 2, 3])
    assert fp.version == 99


def test_compute_simhash() -> None:
    fp_1a = array.array("i", TEST_1A_FP_RAW)
    fp_1b = array.array("i", TEST_1B_FP_RAW)
    fp_1c = array.array("i", TEST_1C_FP_RAW)
    fp_1d = array.array("i", TEST_1D_FP_RAW)
    fp_2 = array.array("i", TEST_2_FP_RAW)

    sh_1 = [
        compute_simhash(fp_1a),
        compute_simhash(fp_1b),
        compute_simhash(fp_1c),
        compute_simhash(fp_1d),
    ]
    sh_2 = compute_simhash(fp_2)

    for i in range(len(sh_1)):
        for j in range(i + 1, len(sh_1)):
            assert sh_1[i] == sh_1[j], f"{i} vs {j}"
        assert sh_1[i] != sh_2, f"{i} vs different song"


def test_compute_shingled_simhashes() -> None:
    fp_1a = array.array("i", TEST_1A_FP_RAW)
    fp_1b = array.array("i", TEST_1B_FP_RAW)
    fp_1c = array.array("i", TEST_1C_FP_RAW)
    fp_1d = array.array("i", TEST_1D_FP_RAW)
    fp_2 = array.array("i", TEST_2_FP_RAW)

    shingle_size = 120
    step = 90

    sh_1 = [
        compute_shingled_simhashes(fp_1a, shingle_size=shingle_size, step=step),
        compute_shingled_simhashes(fp_1b, shingle_size=shingle_size, step=step),
        compute_shingled_simhashes(fp_1c, shingle_size=shingle_size, step=step),
        compute_shingled_simhashes(fp_1d, shingle_size=shingle_size, step=step),
    ]
    sh_2 = compute_shingled_simhashes(fp_2, shingle_size=shingle_size, step=step)

    for i in range(len(sh_1)):
        for j in range(i + 1, len(sh_1)):
            print(f"{i} vs {j}")
            print(sh_1[i])
            print(sh_1[j])
            matches = set(sh_1[i]) & set(sh_1[j])
            assert matches, f"{i} vs {j}"

        matches = set(sh_1[i]) & set(sh_2)
        assert len(matches) == 0, f"{i} vs different song"
