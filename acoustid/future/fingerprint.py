import struct

import zstd

MAGIC = ord("F") << 0 | ord("p") << 8
FORMAT = 1  # version of the binary encoding format


def compress_fingerprint(hashes: list[int], version: int) -> bytes:
    """Compresses a list of fingerprint hashes using zstd compression.

    Args:
        hashes: List of integer hash values representing the fingerprint.
        version: The version of the fingerprint algorithm used to generate the hashes.

    Returns:
        Compressed bytes containing the fingerprint data.

    The function computes XOR differences between consecutive hashes to improve
    compression, packs them into bytes and applies zstd compression.
    """
    diffs = [hashes[i] ^ (hashes[i - 1] if i > 0 else 0) for i in range(len(hashes))]
    data = struct.pack(f"<HBB{len(diffs)}i", MAGIC, FORMAT, version, *diffs)
    return zstd.compress(data, 0)


def decompress_fingerprint(data: bytes) -> tuple[list[int], int]:
    """Decompresses fingerprint data back into a list of hash values.

    Args:
        data: Compressed bytes containing the fingerprint data.

    Returns:
        Tuple containing a list of integer hash values and the version of the fingerprint.

    The function decompresses the zstd data, unpacks the bytes into integers,
    and reconstructs the original hash values by reversing the XOR differences.
    """
    data = zstd.decompress(data)
    magic, format, version, *diffs = struct.unpack(f"<HBB{len(data) // 4 - 1}i", data)
    if magic != MAGIC:
        raise ValueError(f"Invalid fingerprint magic: {magic:#x}, expected: {MAGIC:#x}")
    if format != FORMAT:
        raise ValueError(f"Invalid format version: {format}, expected: {FORMAT}")
    hashes: list[int] = [0] * len(diffs)
    last_hash = 0
    for i, h in enumerate(diffs):
        last_hash = h ^ last_hash
        hashes[i] = last_hash
    return hashes, version
