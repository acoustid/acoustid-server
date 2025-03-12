import array
from typing import NamedTuple

class Fingerprint(NamedTuple):
    hashes: array.array[int]
    version: int

class FingerprintError(Exception): ...

def encode_fingerprint(
    hashes: list[int] | array.array[int], version: int, signed: bool = False
) -> bytes: ...
def decode_fingerprint(data: bytes, signed: bool = False) -> Fingerprint: ...
def encode_legacy_fingerprint(
    fingerprint: list[int] | array.array[int],
    algorithm: int,
    base64: bool = True,
    signed: bool = False,
) -> bytes: ...
def decode_legacy_fingerprint(
    data: bytes, base64: bool = True, signed: bool = False
) -> Fingerprint: ...
