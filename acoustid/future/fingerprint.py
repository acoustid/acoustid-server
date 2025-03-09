import zstd

from acoustid._ext import encode_fingerprint, decode_fingerprint


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
    data = encode_fingerprint(hashes, version)
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

    try:
        data = zstd.decompress(data)
    except zstd.Error as e:
        raise ValueError(f"Failed to decompress fingerprint: {e}") from e

    return decode_fingerprint(data)
