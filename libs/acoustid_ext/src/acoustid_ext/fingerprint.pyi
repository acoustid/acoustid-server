import array

def encode_fingerprint(
    hashes: list[int] | array.array[int], version: int, signed: bool = False
) -> bytes: ...
def decode_fingerprint(
    data: bytes, signed: bool = False
) -> tuple[array.array[int], int]: ...
