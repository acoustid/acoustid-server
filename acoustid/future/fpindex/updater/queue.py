import msgspec

STREAM_NAME = "fpindex"
SUBJECT_NAME = "fpindex.changes"


# Field name mapping for compact messages:
# Base:
#   o = operation (I, U, D)
#   x = transaction id (xid)
#   l = log sequence number (lsn)
# Operations:
#   i = fingerprint id
#   q = fingerprint hashes (using compression from chromaprint)
#   s = simhash of fingerprint hashes


class Base(msgspec.Struct, tag_field="o"):
    xid: int = msgspec.field(name="x")
    lsn: int = msgspec.field(name="l")


class FingerprintInsert(Base, tag="I"):
    id: int = msgspec.field(name="i")
    query: bytes = msgspec.field(name="q")
    simhash: int = msgspec.field(name="s")


class FingerprintUpdate(Base, tag="U"):
    id: int = msgspec.field(name="i")
    query: bytes = msgspec.field(name="q")
    simhash: int = msgspec.field(name="s")


class FingerprintDelete(Base, tag="D"):
    id: int = msgspec.field(name="i")


FingerprintChange = FingerprintInsert | FingerprintUpdate | FingerprintDelete
