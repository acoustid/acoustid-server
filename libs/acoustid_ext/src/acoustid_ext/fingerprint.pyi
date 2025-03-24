# fmt: off

import array
from typing import Literal, NamedTuple, overload

class Fingerprint(NamedTuple):
    hashes: array.array[int]
    version: int


class FingerprintError(Exception):
    ...


def encode_fingerprint(
    hashes: list[int] | array.array[int], version: int, signed: bool = False
) -> bytes:
    ...


def decode_fingerprint(data: bytes, signed: bool = False) -> Fingerprint:
    ...


@overload
def encode_legacy_fingerprint(
    fingerprint: list[int] | array.array[int],
    algorithm: int,
    base64: Literal[True] = True,
    signed: bool = False,
) -> str: ...

@overload
def encode_legacy_fingerprint(
    fingerprint: list[int] | array.array[int],
    algorithm: int,
    base64: Literal[False],
    signed: bool = False,
) -> bytes: ...


@overload
def decode_legacy_fingerprint(
    data: str | bytes,
    base64: Literal[True] = True,
    signed: bool = False,
) -> Fingerprint: ...

@overload
def decode_legacy_fingerprint(
    data: bytes,
    base64: Literal[False],
    signed: bool = False,
) -> Fingerprint: ...


def compute_simhash(
    hashes: array.array[int],
    signed: bool = False,
) -> int: ...


def compute_shingled_simhashes(
    hashes: array.array[int],
    shingle_size: int,
    step: int,
    signed: bool = False,
) -> array.array[int]: ...
