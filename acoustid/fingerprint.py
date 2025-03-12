import zstd
from acoustid_ext.fingerprint import decode_fingerprint, encode_fingerprint


def to_unsigned(hashes: list[int]) -> list[int]:
    return [h & 0xFFFFFFFF for h in hashes]


def to_signed(hashes: list[int]) -> list[int]:
    return [h - 0x100000000 if h & 0x80000000 else h for h in hashes]


NUM_QUERY_BITS = 28
QUERY_BIT_MASK = ((1 << NUM_QUERY_BITS) - 1) << (32 - NUM_QUERY_BITS)
SILENCE_HASH = 627964279


def extract_query(hashes: list[int], size: int = 120, start: int = 80) -> list[int]:
    """Extracts a subset of fingerprint hashes for querying.

    Args:
        hashes: List of integer hash values representing the fingerprint.
        size: Target size for the query, defaults to 120.
        start: Starting index for the query, defaults to 80.

    Returns:
        A list of hash values to be used for querying.

    The function filters out silence hashes, masks each hash to keep
    only the most significant bits, and ensures uniqueness in the result.
    """

    if size <= 0:
        return []

    # Count non-silence hashes
    clean_size = sum(1 for hash in hashes if hash & 0xFFFFFFFF != SILENCE_HASH)

    if clean_size <= 0:
        return []

    query = [0] * size
    query_hashes = set()
    query_size = 0

    start_idx = max(0, min(clean_size - size, start))

    for i in range(start_idx, len(hashes)):
        if query_size >= size:
            break

        hash_val = hashes[i] & 0xFFFFFFFF
        if hash_val == SILENCE_HASH:
            continue

        hash_val &= QUERY_BIT_MASK

        if hash_val in query_hashes:
            continue

        query_hashes.add(hash_val)
        query[query_size] = hash_val
        query_size += 1

    return query[:query_size]


def compress_fingerprint(
    hashes: list[int], version: int, *, signed: bool = False
) -> bytes:
    """Compresses a list of fingerprint hashes using zstd compression.

    Args:
        hashes: List of integer hash values representing the fingerprint.
        version: The version of the fingerprint algorithm used to generate the hashes.
        signed: Whether the hashes are signed or unsigned.

    Returns:
        Compressed bytes containing the fingerprint data.

    The function computes XOR differences between consecutive hashes to improve
    compression, packs them into bytes and applies zstd compression.
    """
    data = encode_fingerprint(hashes, version, signed)
    return zstd.compress(data, 0)


def decompress_fingerprint(
    data: bytes, *, signed: bool = False
) -> tuple[list[int], int]:
    """Decompresses fingerprint data back into a list of hash values.

    Args:
        data: Compressed bytes containing the fingerprint data.
        signed: Whether the hashes are signed or unsigned.

    Returns:
        Tuple containing a list of integer hash values and the version of the fingerprint.

    The function decompresses the zstd data, unpacks the bytes into integers,
    and reconstructs the original hash values by reversing the XOR differences.
    """

    try:
        data = zstd.decompress(data)
    except zstd.Error as e:
        raise ValueError(f"Failed to decompress fingerprint: {e}") from e

    hashes, version = decode_fingerprint(data, signed)
    return list(hashes), version
