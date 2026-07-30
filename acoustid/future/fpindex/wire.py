# Copyright (C) 2026 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

"""Wire types for the fpindex changelog feed.

fpindex's RemoteCoordinator (src/RemoteCoordinator.zig) decodes these with
msgpack.zig, and every struct in that protocol declares

    .{ .as_map = .{ .key = .{ .field_name_prefix = 1 } } }

which means each field is keyed by the first character of its name --
`strPrefix(field.name, 1)` in msgpack.zig's struct.zig. Rather than hand-write
those letters, `_field_name_prefix` below states the same rule once and msgspec
applies it, so the field names here stay readable and can be checked against the
Zig struct definitions field for field.

    ReadResponse{ entries, retry_after_ms } -> {"e": [...], "r": u64}
    Entry{ id, change }                     -> {"i": u64, "c": Change}
    Change (tagged union, as_map)           -> {"i": Insert} | {"d": Delete}
    Insert{ id, hashes }                    -> {"i": u32, "h": [u32, ...]}
    Delete{ id }                            -> {"i": u32}

The union is the one thing msgspec cannot express natively: msgpack.zig writes a
tagged union as a **one-element map keyed by the variant name**, whereas
msgspec's tagged unions put a tag field inside the struct. So `Change` is a
`dict` with a single entry, built by the two helpers below.

Note the hazard the prefix scheme carries: two fields of one struct whose names
share a first letter would collide. msgspec raises at class-definition time if a
rename produces duplicates, so it fails loudly rather than emitting a broken
map -- but it is worth knowing before adding a field.

Nothing here relies on integer width. msgpack decoders accept any width for a
given value, so the encoder is free to pick the smallest; what must match is the
structure and the keys.

The meta feed adds:

    MetaReadResponse{ ops, retry_after_ms } -> {"o": [...], "r": u64}
    MetaOp{ pos, kind, index_name }         -> {"p": u64, "k": u8, "i": str}

`kind` is a Zig `enum(u8)` and goes on the wire as its **integer** tag, not its
name: msgpack.zig's packEnum is `packInt(writer, tag_type, @intFromEnum(value))`.
(Checked against msgpack 0.7.0, which is what ng pins. 0.1.0 has no enum support
at all, so a struct like this would not even compile against it.)
"""

import enum
from typing import Sequence, Union

import msgspec

# The one index in this deployment. The changelog's global sequence is therefore
# also that index's position sequence -- with a single lineage the distinction
# collapses, which is why there is no per-lineage sequence anywhere.
INDEX_NAME = "acoustid"

# Lineage identity. In the Zig protocol a generation comes from the position of
# the index's `create` op on the meta feed; with one index created once it is a
# constant. It is still checked on every request: a consumer carrying a different
# generation is talking about a different lineage and must be told so rather than
# silently fed this one's data.
GENERATION = 1


def _field_name_prefix(name: str) -> str:
    """msgpack.zig's `field_name_prefix = 1`, as a msgspec rename rule."""
    return name[0]


class Insert(msgspec.Struct, rename=_field_name_prefix):
    id: int
    hashes: list[int]


class Delete(msgspec.Struct, rename=_field_name_prefix):
    id: int


# msgpack.zig serializes a tagged union as a one-element map keyed by the variant
# name, put through the same prefix rule: insert -> "i", delete -> "d".
Change = dict[str, Union[Insert, Delete]]


def insert_change(fingerprint_id: int, hashes: Sequence[int]) -> Change:
    return {"i": Insert(id=fingerprint_id, hashes=list(hashes))}


def delete_change(fingerprint_id: int) -> Change:
    """Unused by the changelog today -- the trigger is AFTER INSERT only, since
    fingerprints are never deleted -- but part of the protocol, and cheap to keep
    correct next to its counterpart."""
    return {"d": Delete(id=fingerprint_id)}


class Entry(msgspec.Struct, rename=_field_name_prefix):
    id: int
    change: Change


class ReadResponse(msgspec.Struct, rename=_field_name_prefix):
    entries: list[Entry]
    # How long the consumer should wait before asking again. The server answers
    # immediately and paces the consumer with this, instead of the consumer
    # passing a timeout and the server holding the connection open.
    retry_after_ms: int


def encode(response: ReadResponse) -> bytes:
    return msgspec.msgpack.encode(response)


def changelog_response(
    rows: Sequence[tuple[int, int, Sequence[int]]], retry_after_ms: int
) -> ReadResponse:
    """Build a response from `(position, fingerprint_id, query)` rows."""
    return ReadResponse(
        entries=[
            Entry(id=position, change=insert_change(fingerprint_id, query))
            for position, fingerprint_id, query in rows
        ],
        retry_after_ms=retry_after_ms,
    )


class MetaOpKind(enum.IntEnum):
    """Zig `enum(u8) { create, delete }` -- ordinal order is the wire value."""

    create = 0
    delete = 1


class MetaOp(msgspec.Struct, rename=_field_name_prefix):
    pos: int
    kind: MetaOpKind
    index_name: str


class MetaReadResponse(msgspec.Struct, rename=_field_name_prefix):
    ops: list[MetaOp]
    retry_after_ms: int


# The whole meta feed for this deployment: one index, created once, never
# deleted. `pos` for a create IS the generation, per the protocol -- so the
# constant below and GENERATION are necessarily the same number rather than two
# things that have to be kept in step.
THE_INDEX_WAS_CREATED_AT = GENERATION

META_OPS = [
    MetaOp(
        pos=THE_INDEX_WAS_CREATED_AT,
        kind=MetaOpKind.create,
        index_name=INDEX_NAME,
    )
]


def meta_response(after: int, limit: int, retry_after_ms: int) -> MetaReadResponse:
    """The meta feed is never truncated, so `after` is a plain filter."""
    ops = [op for op in META_OPS if op.pos > after][:limit]
    return MetaReadResponse(ops=ops, retry_after_ms=retry_after_ms)


def encode_meta(response: MetaReadResponse) -> bytes:
    return msgspec.msgpack.encode(response)


class BootstrapHeader(msgspec.Struct, rename=_field_name_prefix):
    """First value in a bootstrap stream.

    `position` is the changelog position the streamed state corresponds to, taken
    before the first chunk is read. The node applies every change in the stream at
    this one position and resumes the feed from it.
    """

    position: int


def encode_bootstrap_header(position: int) -> bytes:
    return msgspec.msgpack.encode(BootstrapHeader(position=position))


def encode_change(change: Change) -> bytes:
    """One value in the bootstrap stream, framed only by msgpack itself.

    msgpack values are self-delimiting, so a reader decodes them one after another
    off the socket without a length prefix or separator.
    """
    return msgspec.msgpack.encode(change)
