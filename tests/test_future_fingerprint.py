import base64

from acoustid.future.fingerprint import compress_fingerprint, decompress_fingerprint
from tests import TEST_2_FP_RAW


def test_compress_decompress() -> None:
    compressed = compress_fingerprint(TEST_2_FP_RAW, 1)
    assert len(base64.b64encode(compressed)) < len(TEST_2_FP_RAW) * 4
    hashes, version = decompress_fingerprint(compressed)
    assert hashes == TEST_2_FP_RAW
    assert version == 1
