import base64
import struct

import pytest
import zstd
from acoustid_ext.fingerprint import (
    decode_legacy_fingerprint,
    encode_legacy_fingerprint,
)

from acoustid.fingerprint import (
    compress_fingerprint,
    decompress_fingerprint,
    to_signed,
    to_unsigned,
)
from tests import TEST_2_FP, TEST_2_FP_RAW


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
