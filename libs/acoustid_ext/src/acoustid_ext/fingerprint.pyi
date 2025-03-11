import array
from typing import NamedTuple

class Fingerprint(NamedTuple):
    hashes: array.array[int]
    version: int

def encode_fingerprint(
    hashes: list[int] | array.array[int], version: int, signed: bool = False
) -> bytes: ...
def decode_fingerprint(data: bytes, signed: bool = False) -> Fingerprint: ...
