import base64
import struct
import uuid

import pytest
import zstd
from acoustid_ext.fingerprint import (
    decode_legacy_fingerprint,
    encode_legacy_fingerprint,
)

from acoustid.fingerprint import (
    compress_fingerprint,
    decompress_fingerprint,
    process_fingerprint,
    to_signed,
    to_unsigned,
)
from tests import (
    TEST_1A_FP,
    TEST_1A_FP_RAW,
    TEST_1B_FP,
    TEST_1B_FP_RAW,
    TEST_2_FP,
    TEST_2_FP_RAW,
)


def test_compress_decompress_signed() -> None:
    hashes = TEST_2_FP_RAW

    compressed = compress_fingerprint(hashes, 1, signed=True)
    assert len(base64.b64encode(compressed)) < len(hashes) * 4

    out_hashes, out_version = decompress_fingerprint(compressed, signed=True)
    assert out_hashes == hashes
    assert out_version == 1


def test_compress_decompress_unsigned() -> None:
    hashes = to_unsigned(TEST_2_FP_RAW)
    assert to_signed(hashes) == TEST_2_FP_RAW

    compressed = compress_fingerprint(hashes, 1)
    assert len(base64.b64encode(compressed)) < len(hashes) * 4

    out_hashes, out_version = decompress_fingerprint(compressed)
    assert out_hashes == hashes
    assert out_version == 1


def test_decompress_invalid_data() -> None:
    with pytest.raises(ValueError, match="Failed to decompress fingerprint"):
        decompress_fingerprint(b"invalid data")

    with pytest.raises(ValueError, match="Invalid fingerprint magic"):
        decompress_fingerprint(zstd.compress(struct.pack("<ccBB", b"A", b"a", 1, 1)))

    with pytest.raises(ValueError, match="Invalid format version"):
        decompress_fingerprint(zstd.compress(struct.pack("<ccBB", b"F", b"p", 0, 1)))


def test_decode_legacy_fingerprint() -> None:
    fp = decode_legacy_fingerprint(TEST_2_FP, base64=True, signed=True)
    assert list(fp.hashes) == TEST_2_FP_RAW
    assert fp.version == 1


def test_encode_legacy_fingerprint() -> None:
    data = encode_legacy_fingerprint(TEST_2_FP_RAW, 1, base64=True, signed=True)
    assert data == TEST_2_FP


def test_process_fingerprint() -> None:
    fp = process_fingerprint(TEST_1A_FP)
    assert fp.version == 1
    assert fp.hashes.tolist() == TEST_1A_FP_RAW
    assert fp.gid == uuid.UUID("10536e2c-5058-585c-b6d1-f2a6efd4001b")
    assert fp.simhash == 2641753427

    fp = process_fingerprint(TEST_1B_FP)
    assert fp.version == 1
    assert fp.hashes.tolist() == TEST_1B_FP_RAW
    assert fp.gid == uuid.UUID("f2acf5a8-0231-5214-a3cf-6d0ab2041a76")
    assert fp.simhash == 2641753427

    fp = process_fingerprint(TEST_2_FP)
    assert fp.version == 1
    assert fp.hashes.tolist() == TEST_2_FP_RAW
    assert fp.gid == uuid.UUID("756542b4-ab5d-568a-bc4e-3d7cd6dc8e56")
    assert fp.simhash == 3228088686
