import base64
import struct

import pytest
import zstd

from acoustid.future.fingerprint import (
    compress_fingerprint,
    decompress_fingerprint,
)
from tests import TEST_2_FP_RAW


def test_compress_decompress() -> None:
    compressed = compress_fingerprint(TEST_2_FP_RAW, 1)
    assert len(base64.b64encode(compressed)) < len(TEST_2_FP_RAW) * 4
    hashes, version = decompress_fingerprint(compressed)
    for h1, h2 in zip(hashes, TEST_2_FP_RAW):
        print(h1, h2)
    assert hashes == TEST_2_FP_RAW
    assert version == 1


def test_decompress_invalid_data() -> None:
    with pytest.raises(ValueError, match="Failed to decompress fingerprint"):
        decompress_fingerprint(b"invalid data")

    with pytest.raises(ValueError, match="Invalid fingerprint magic"):
        decompress_fingerprint(zstd.compress(struct.pack("<ccBB", b"A", b"a", 1, 1)))

    with pytest.raises(ValueError, match="Invalid format version"):
        decompress_fingerprint(zstd.compress(struct.pack("<ccBB", b"F", b"p", 0, 1)))
