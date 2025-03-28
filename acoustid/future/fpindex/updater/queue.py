import msgspec

STREAM_NAME = "fpindex"


class Base(msgspec.Struct, tag_field="o"):
    xid: int = msgspec.field(name="x")
    lsn: int = msgspec.field(name="l")


class FingerprintInsert(Base, tag="I"):
    id: int = msgspec.field(name="i")
    hashes: bytes = msgspec.field(name="h")


class FingerprintUpdate(Base, tag="U"):
    id: int = msgspec.field(name="i")
    hashes: bytes = msgspec.field(name="h")


class FingerprintDelete(Base, tag="D"):
    id: int = msgspec.field(name="i")


FingerprintChange = FingerprintInsert | FingerprintUpdate | FingerprintDelete
