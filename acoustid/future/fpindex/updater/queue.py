import msgspec

STREAM_NAME = "fpindex"


class BaseOp(msgspec.Struct, tag_field="op"):
    xid: int
    lsn: int


class FingerprintInsert(BaseOp, tag="I"):
    id: int
    hashes: bytes


class FingerprintUpdate(BaseOp, tag="U"):
    id: int
    hashes: bytes


class FingerprintDelete(BaseOp, tag="D"):
    id: int


class Commit(BaseOp, tag="C"):
    pass


FingerprintChange = FingerprintInsert | FingerprintUpdate | FingerprintDelete
