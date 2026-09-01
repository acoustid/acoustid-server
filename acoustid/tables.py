import datetime

import sqlalchemy.event
from sqlalchemy import (
    DDL,
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    MetaData,
    PrimaryKeyConstraint,
    Sequence,
    SmallInteger,
    String,
    Table,
    Text,
    sql,
)
from sqlalchemy.dialects.postgresql import ARRAY, INET, JSONB, UUID
from sqlalchemy.engine import Connection
from sqlalchemy.types import UserDefinedType

metadata = MetaData(
    naming_convention={
        "fk": "%(table_name)s_fk_%(column_0_name)s",
        "ix": "%(table_name)s_idx_%(column_0_name)s",
        "pk": "%(table_name)s_pkey",
    }
)

import mbdata.config  # noqa: E402

mbdata.config.configure(metadata=metadata, schema="musicbrainz")

sqlalchemy.event.listen(
    metadata,
    "before_create",
    DDL("CREATE SCHEMA IF NOT EXISTS musicbrainz"),
)

account = Table(
    "account",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String, nullable=False),
    Column("apikey", String, nullable=False),
    Column("mbuser", String),
    Column("anonymous", Boolean, default=False, server_default=sql.false()),
    Column(
        "created",
        DateTime(timezone=True),
        server_default=sql.func.current_timestamp(),
        nullable=False,
    ),
    Column("lastlogin", DateTime(timezone=True)),
    Column("submission_count", Integer, nullable=False, server_default=sql.literal(0)),
    Column("application_id", Integer, ForeignKey("application.id", use_alter=True)),
    Column("application_version", String),
    Column("created_from", INET),
    Column(
        "is_admin", Boolean, default=False, server_default=sql.false(), nullable=False
    ),
    Index("account_idx_mbuser", "mbuser", unique=True),
    Index("account_idx_apikey", "apikey", unique=True),
    info={"bind_key": "app"},
)

account_openid = Table(
    "account_openid",
    metadata,
    Column("openid", String, primary_key=True),
    Column("account_id", Integer, ForeignKey("account.id"), nullable=False),
    Index("account_openid_idx_account_id", "account_id"),
    info={"bind_key": "app"},
)

account_google = Table(
    "account_google",
    metadata,
    Column("google_user_id", String, primary_key=True),
    Column("account_id", Integer, ForeignKey("account.id"), nullable=False),
    Index("account_google_idx_account_id", "account_id"),
    info={"bind_key": "app"},
)

application = Table(
    "application",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String, nullable=False),
    Column("version", String, nullable=False),
    Column("apikey", String, nullable=False),
    Column(
        "created",
        DateTime(timezone=True),
        server_default=sql.func.current_timestamp(),
        nullable=False,
    ),
    Column("active", Boolean, default=True, server_default=sql.true()),
    Column("account_id", Integer, ForeignKey("account.id"), nullable=False),
    Column("email", String),
    Column("website", String),
    Index("application_idx_apikey", "apikey", unique=True),
    info={"bind_key": "app"},
)

track = Table(
    "track",
    metadata,
    Column("id", Integer, primary_key=True),
    Column(
        "created",
        DateTime(timezone=True),
        server_default=sql.func.current_timestamp(),
        nullable=False,
    ),
    Column("updated", DateTime(timezone=True)),
    Column("new_id", Integer, ForeignKey("track.id")),
    Column("gid", UUID, nullable=False),
    Index("track_idx_gid", "gid", unique=True),
    info={"bind_key": "fingerprint"},
)

format = Table(
    "format",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String, nullable=False),
    Index("format_idx_name", "name", unique=True),
    info={"bind_key": "app"},
)

source = Table(
    "source",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("application_id", Integer, ForeignKey("application.id"), nullable=False),
    Column("account_id", Integer, ForeignKey("account.id"), nullable=False),
    Column("version", String),
    Index("source_idx_uniq", "application_id", "account_id", "version", unique=True),
    info={"bind_key": "app"},
)

pending_submission = Table(
    "pending_submission",
    metadata,
    Column("id", Integer, primary_key=True),
    info={"bind_key": "ingest"},
)

submission = Table(
    "submission",
    metadata,
    Column("id", Integer, primary_key=True),
    # status
    Column(
        "created",
        DateTime(timezone=True),
        server_default=sql.func.current_timestamp(),
        nullable=False,
    ),
    Column("handled_at", DateTime(timezone=True)),
    Column("handled", Boolean, default=False, server_default=sql.false()),
    # source
    Column("account_id", Integer, nullable=True),
    Column("application_id", Integer, nullable=True),
    Column("application_version", String),
    Column("source_id", Integer, nullable=True),  # XXX deprecated
    # fingerprint
    Column("fingerprint", ARRAY(Integer), nullable=False),
    Column("length", SmallInteger, CheckConstraint("length>0"), nullable=False),
    Column("bitrate", SmallInteger, CheckConstraint("bitrate>0")),
    Column("format", String),
    Column("format_id", Integer),  # XXX deprecated
    # metadata
    Column("meta", JSONB),
    Column("meta_gid", UUID(as_uuid=True)),
    Column("meta_id", Integer),  # XXX deprecated
    Column("mbid", UUID),
    Column("puid", UUID),
    Column("foreignid", String),
    Column("foreignid_id", Integer),  # XXX deprecated
    info={"bind_key": "ingest"},
)

Index(
    "submission_idx_handled",
    submission.c.id,
    postgresql_where=submission.c.handled == False,  # noqa: E712
)

submission_result = Table(
    "submission_result",
    metadata,
    Column("submission_id", Integer, primary_key=True, autoincrement=False),
    # status
    Column("created", DateTime(timezone=True), nullable=False),
    Column("handled_at", DateTime(timezone=True), nullable=True),
    # source
    Column("account_id", Integer, nullable=False),
    Column("application_id", Integer, nullable=False),
    Column("application_version", String),
    # fingerprint
    Column("fingerprint_id", Integer, nullable=False),
    Column("track_id", Integer, nullable=False),
    # metadata
    Column("meta_gid", UUID(as_uuid=True)),
    Column("meta_id", Integer),
    Column("mbid", UUID),
    Column("puid", UUID),
    Column("foreignid", String),
    info={"bind_key": "ingest"},
)

stats = Table(
    "stats",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String, nullable=False),
    Column("date", Date, server_default=sql.func.current_date(), nullable=False),
    Column("value", Integer, nullable=False),
    Index("stats_idx_date", "date"),
    Index("stats_idx_name_date", "name", "date"),
    info={"bind_key": "app"},
)

stats_lookups = Table(
    "stats_lookups",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("date", Date, nullable=False),
    Column("hour", Integer, nullable=False),
    Column("application_id", Integer, ForeignKey("application.id"), nullable=False),
    Column(
        "count_nohits",
        Integer,
        default=0,
        server_default=sql.literal(0),
        nullable=False,
    ),
    Column(
        "count_hits", Integer, default=0, server_default=sql.literal(0), nullable=False
    ),
    Index("stats_lookups_idx_date", "date"),
    info={"bind_key": "app"},
)

stats_user_agents = Table(
    "stats_user_agents",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("date", Date, nullable=False),
    Column("application_id", Integer, ForeignKey("application.id"), nullable=False),
    Column("user_agent", String, nullable=False),
    Column("ip", String, nullable=False),
    Column("count", Integer, default=0, server_default=sql.literal(0), nullable=False),
    Index("stats_user_agents_idx_date", "date"),
    info={"bind_key": "app"},
)

stats_top_accounts = Table(
    "stats_top_accounts",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("account_id", Integer, ForeignKey("account.id"), nullable=False),
    Column("count", Integer, nullable=False),
    info={"bind_key": "app"},
)

meta = Table(
    "meta",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("track", String),
    Column("artist", String),
    Column("album", String),
    Column("album_artist", String),
    Column("track_no", Integer),
    Column("disc_no", Integer),
    Column("year", Integer),
    Column(
        "created",
        DateTime(timezone=True),
        server_default=sql.func.current_timestamp(),
        nullable=False,
    ),
    Column("gid", UUID(as_uuid=True), unique=True, index=True),
    info={"bind_key": "fingerprint"},
)

meta_id_history = Table(
    "meta_id_history",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("gid", UUID(as_uuid=True), index=True),
    info={"bind_key": "fingerprint"},
)

foreignid_vendor = Table(
    "foreignid_vendor",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String, nullable=False),
    Index("foreignid_vendor_idx_name", "name", unique=True),
    info={"bind_key": "fingerprint"},
)

foreignid = Table(
    "foreignid",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("vendor_id", Integer, ForeignKey("foreignid_vendor.id"), nullable=False),
    Column("name", Text, nullable=False),
    Index("foreignid_idx_vendor", "vendor_id"),
    Index("foreignid_idx_vendor_name", "vendor_id", "name", unique=True),
    info={"bind_key": "fingerprint"},
)

foreignid.add_is_dependent_on(foreignid_vendor)

fingerprint = Table(
    "fingerprint",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("fingerprint", ARRAY(Integer), nullable=False),
    Column("length", SmallInteger, CheckConstraint("length>0"), nullable=False),
    Column("bitrate", SmallInteger, CheckConstraint("bitrate>0")),
    Column("format_id", Integer),
    Column(
        "created",
        DateTime(timezone=True),
        server_default=sql.func.current_timestamp(),
        nullable=False,
    ),
    Column("updated", DateTime(timezone=True)),
    Column("track_id", Integer, ForeignKey("track.id"), nullable=False),
    Column("submission_count", Integer, nullable=False),
    Index("fingerprint_idx_length", "length"),
    Index("fingerprint_idx_track_id", "track_id"),
    info={"bind_key": "fingerprint"},
)

fingerprint_data = Table(
    "fingerprint_data",
    metadata,
    Column("id", Integer, ForeignKey("fingerprint.id"), primary_key=True),
    Column("gid", UUID(as_uuid=True), nullable=False, index=True, unique=True),
    Column("fingerprint", LargeBinary, nullable=False),
    Column("simhash", Integer, nullable=False, index=True),
    Column(
        "created",
        DateTime(timezone=True),
        server_default=sql.func.current_timestamp(),
        nullable=False,
    ),
    info={"bind_key": "fingerprint"},
)

fingerprint_source = Table(
    "fingerprint_source",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("fingerprint_id", Integer, nullable=False),
    Column("submission_id", Integer, nullable=False),
    Column("source_id", Integer, nullable=False),
    Column(
        "created",
        DateTime(timezone=True),
        server_default=sql.func.current_timestamp(),
        nullable=False,
    ),
    Index("fingerprint_source_idx_submission_id", "submission_id"),
    info={"bind_key": "ingest"},
)


class XID8(UserDefinedType):
    """PostgreSQL xid8 -- a transaction ID that does not wrap around.

    Unlike the 32-bit xmin system column, xid8 carries the epoch, so values
    stay comparable for the lifetime of the cluster.
    """

    cache_ok = True

    def get_col_spec(self, **kw: object) -> str:
        return "xid8"


# Every writer serialises on this key inside fpindex_changelog_insert(), which
# is what makes the changelog id order equal to the commit order. The value is
# arbitrary but must never change: two different values are two different locks
# and would silently stop serialising writers against each other.
FPINDEX_CHANGELOG_LOCK_KEY = 7723016524936704001

# Changes to the fingerprint table, in commit order, for fpindex to replay.
#
# `id` is the consumer cursor: a consumer tails `WHERE id > cursor ORDER BY id`
# and that is safe ONLY because the trigger takes an advisory lock before the id
# is allocated (see fpindex_changelog_insert below). Without it a transaction
# that grabbed a lower id but committed later would be skipped forever, which is
# the bug in the old index updater.
#
# Partitioned by `created` so retention is a calendar job: dropping whole
# partitions keeps vacuum out of the picture entirely, and a create-ahead job
# working on dates cannot be caught out by a change in write volume the way an
# id-range one could.
#
# Monthly, not daily. At the current rate -- around 13.5k new fingerprints a
# day -- a month is roughly 400k rows, which is a perfectly ordinary table, and
# the create-ahead job only has real work to do twelve times a year instead of
# 365. That matters more than it sounds: creating a partition takes ACCESS
# EXCLUSIVE on the parent, which queues the trigger's own inserts behind it.
#
# `created` uses clock_timestamp(), NOT now(): now() is transaction start time,
# so a long transaction would file its row under an earlier partition than its
# id-neighbours and the retained rows would stop being a contiguous id range.
# Taken inside the advisory lock, clock_timestamp() advances in the same order
# as the id, so time partitions and an id cursor agree.
fpindex_changelog = Table(
    "fpindex_changelog",
    metadata,
    Column(
        "id",
        BigInteger,
        Sequence("fpindex_changelog_id_seq", metadata=metadata),
        server_default=sql.text("nextval('fpindex_changelog_id_seq')"),
        nullable=False,
    ),
    Column("fingerprint_id", Integer, nullable=False),
    Column("query", ARRAY(Integer), nullable=False),
    # Diagnostic, and it keeps the xmin-horizon read strategy available without
    # a migration if the advisory lock ever needs to come out.
    Column(
        "xid",
        XID8,
        server_default=sql.text("pg_current_xact_id()"),
        nullable=False,
    ),
    Column(
        "created",
        DateTime(timezone=True),
        server_default=sql.text("clock_timestamp()"),
        nullable=False,
    ),
    # A partitioned table may only have a unique constraint that covers the
    # partition key, so the primary key is the pair. `id` alone is still unique
    # -- it comes from a sequence -- and leads the index, which is what the
    # consumer's `id > cursor` scan needs.
    PrimaryKeyConstraint("id", "created"),
    postgresql_partition_by="RANGE (created)",
    info={"bind_key": "fingerprint"},
)


# What retention threw away, so a consumer can tell that it did.
#
# The changelog on its own cannot express this. A consumer tailing
# `WHERE id > cursor` that has fallen behind the retention window gets back an
# empty result -- exactly what it gets when it is up to date. Nothing in the log
# distinguishes "no changes since your cursor" from "the changes since your
# cursor were dropped a fortnight ago", and the second one silently produces an
# index that is missing fingerprints forever.
#
# So retention records the highest row it removed before removing it. A consumer
# at `cursor` is safe if and only if `cursor >= last_deleted_id`; below that the
# ids in `(cursor, last_deleted_id]` are gone and it has to bootstrap from a peer
# snapshot instead of from the log. No row at all means nothing has ever been
# deleted and any cursor is still resumable.
#
# `last_deleted_created` and `last_deleted_xid` are carried for the same reason
# the changelog carries them: diagnostics, and they keep a snapshot-horizon read
# strategy possible without another migration.
#
# One row, enforced. This mirrors the changelog's own decision not to carry a
# lineage dimension -- there is one stream, so there is one watermark. If a
# per-index or per-generation dimension ever arrives, both tables gain it
# together.
fpindex_meta = Table(
    "fpindex_meta",
    metadata,
    Column("singleton", Boolean, primary_key=True, server_default=sql.true()),
    Column("last_deleted_id", BigInteger, nullable=False),
    Column("last_deleted_created", DateTime(timezone=True), nullable=False),
    Column("last_deleted_xid", XID8, nullable=False),
    Column(
        "updated",
        DateTime(timezone=True),
        server_default=sql.text("clock_timestamp()"),
        nullable=False,
    ),
    CheckConstraint("singleton", name="fpindex_meta_singleton"),
    info={"bind_key": "fingerprint"},
)


# There is deliberately no DEFAULT partition.
#
# A default partition looks like a safe backstop and is the opposite. Rows that
# land in it permanently block creating the dated partition that would have
# covered them, retention can never reclaim them because it only drops dated
# partitions, and writes keep succeeding the whole time, so nothing pages. The
# failure it is meant to prevent -- an insert with nowhere to go -- is not
# actually an outage here: insert_fingerprint() is only ever reached from the
# importer, the submission is already durable in the ingest database, and
# pending_submission is cleared in the same transaction that would fail. So the
# row stays queued and retries. Loud and self-healing beats silent and
# hand-repairable, and dropping the default partition also keeps
# DETACH PARTITION ... CONCURRENTLY available if retention ever needs it.
#
# What it costs: the partitions have to actually be there. See
# acoustid.scripts.fpindex_changelog.
FPINDEX_CHANGELOG_CREATE_AHEAD_MONTHS = 12


def fpindex_changelog_month(day: datetime.date) -> datetime.date:
    """The partition a date belongs to, identified by its first day."""
    return day.replace(day=1)


def fpindex_changelog_add_months(month: datetime.date, count: int) -> datetime.date:
    index = month.year * 12 + (month.month - 1) + count
    return datetime.date(index // 12, index % 12 + 1, 1)


def fpindex_changelog_partition_name(month: datetime.date) -> str:
    return "fpindex_changelog_" + month.strftime("%Y%m")


def fpindex_changelog_create_partition_sql(month: datetime.date) -> str:
    """DDL for the partition covering `month`.

    The bounds are formatted into the statement rather than bound as
    parameters. Partition bounds are DDL, and the parameterised form only works
    at all because psycopg2 binds client-side -- it would break the day
    anything here moves to psycopg3 or asyncpg. The values come from date
    arithmetic, never from input.
    """
    end = fpindex_changelog_add_months(month, 1)
    return (
        f"CREATE TABLE IF NOT EXISTS {fpindex_changelog_partition_name(month)} "
        f"PARTITION OF fpindex_changelog "
        f"FOR VALUES FROM ('{month.isoformat()}') TO ('{end.isoformat()}')"
    )


# Kept in sync by hand with the alembic migration that introduces it. Migrations
# must not import this module -- they have to keep working as the models move --
# so the DDL is written out twice on purpose.
FPINDEX_CHANGELOG_DDL = f"""
CREATE OR REPLACE FUNCTION fpindex_changelog_insert() RETURNS trigger AS $$
BEGIN
    PERFORM pg_advisory_xact_lock({FPINDEX_CHANGELOG_LOCK_KEY});
    INSERT INTO fpindex_changelog (fingerprint_id, query)
        VALUES (NEW.id, acoustid_extract_query(NEW.fingerprint));
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS fingerprint_fpindex_changelog ON fingerprint;

CREATE TRIGGER fingerprint_fpindex_changelog
    AFTER INSERT ON fingerprint
    FOR EACH ROW
    EXECUTE FUNCTION fpindex_changelog_insert();
"""


def _create_fpindex_changelog(
    target: MetaData, connection: Connection, **kw: object
) -> None:
    """Partitions first, then the trigger.

    Attached to the metadata rather than to fpindex_changelog because the
    trigger is created on `fingerprint`, and only a metadata-level hook is
    guaranteed to run after every table exists. There is deliberately no
    foreign key from the changelog to the fingerprint: it is a log, and an FK
    would both cost writes and stand in the way of dropping partitions.

    The partitions matter here specifically because there is no DEFAULT to
    catch a row that misses: create_all builds dev and test databases, where
    nothing runs the hourly maintenance task, so without this the first
    fingerprint insert would fail. The server's calendar is used, not this
    process's, for the same reason the maintenance task uses it.
    """
    today = connection.execute(sql.text("SELECT current_date")).scalar_one()
    month = fpindex_changelog_month(today)
    for offset in range(FPINDEX_CHANGELOG_CREATE_AHEAD_MONTHS + 1):
        connection.execute(
            DDL(
                fpindex_changelog_create_partition_sql(
                    fpindex_changelog_add_months(month, offset)
                )
            )
        )
    connection.execute(DDL(FPINDEX_CHANGELOG_DDL))


sqlalchemy.event.listen(metadata, "after_create", _create_fpindex_changelog)


track_mbid = Table(
    "track_mbid",
    metadata,
    Column("track_id", Integer, ForeignKey("track.id"), nullable=False),
    Column("mbid", UUID, nullable=False, index=True),
    Column(
        "created",
        DateTime(timezone=True),
        server_default=sql.func.current_timestamp(),
        nullable=False,
    ),
    Column("updated", DateTime(timezone=True)),
    Column("id", Integer, primary_key=True),
    Column("submission_count", Integer, nullable=False),
    Column(
        "disabled", Boolean, default=False, server_default=sql.false(), nullable=False
    ),
    Column("merged_into", Integer, ForeignKey("track_mbid.id")),
    Index("track_mbid_idx_uniq", "track_id", "mbid", unique=True),
    info={"bind_key": "fingerprint"},
)

track_mbid_source = Table(
    "track_mbid_source",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("track_mbid_id", Integer, nullable=False, index=True),
    Column("submission_id", Integer),
    Column("source_id", Integer, nullable=False, index=True),
    Column(
        "created",
        DateTime(timezone=True),
        server_default=sql.func.current_timestamp(),
        nullable=False,
    ),
    Column("updated", DateTime(timezone=True)),
    info={"bind_key": "ingest"},
)

track_mbid_change = Table(
    "track_mbid_change",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("track_mbid_id", Integer, nullable=False, index=True),
    Column("account_id", Integer, nullable=False),
    Column(
        "created",
        DateTime(timezone=True),
        server_default=sql.func.current_timestamp(),
        nullable=False,
    ),
    Column("disabled", Boolean, nullable=False),
    Column("note", Text),
    Column("updated", DateTime(timezone=True)),
    info={"bind_key": "ingest"},
)

track_puid = Table(
    "track_puid",
    metadata,
    Column("track_id", Integer, ForeignKey("track.id"), nullable=False),
    Column("puid", UUID, nullable=False, index=True),
    Column(
        "created",
        DateTime(timezone=True),
        server_default=sql.func.current_timestamp(),
        nullable=False,
    ),
    Column("updated", DateTime(timezone=True)),
    Column("id", Integer, primary_key=True),
    Column("submission_count", Integer, nullable=False),
    Index("track_puid_idx_uniq", "track_id", "puid", unique=True),
    info={"bind_key": "fingerprint"},
)

track_puid_source = Table(
    "track_puid_source",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("track_puid_id", Integer, nullable=False),
    Column("submission_id", Integer, nullable=False),
    Column("source_id", Integer, nullable=False),
    Column(
        "created",
        DateTime(timezone=True),
        server_default=sql.func.current_timestamp(),
        nullable=False,
    ),
    info={"bind_key": "ingest"},
)

track_meta = Table(
    "track_meta",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("track_id", Integer, ForeignKey("track.id"), nullable=False),
    Column("meta_id", Integer, ForeignKey("meta.id"), nullable=False, index=True),
    Column(
        "created",
        DateTime(timezone=True),
        server_default=sql.func.current_timestamp(),
        nullable=False,
    ),
    Column("updated", DateTime(timezone=True)),
    Column("submission_count", Integer, nullable=False),
    Index("track_meta_idx_uniq", "track_id", "meta_id", unique=True),
    info={"bind_key": "fingerprint"},
)

track_meta_source = Table(
    "track_meta_source",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("track_meta_id", Integer, nullable=False),
    Column("submission_id", Integer, nullable=False),
    Column("source_id", Integer, nullable=False),
    Column(
        "created",
        DateTime(timezone=True),
        server_default=sql.func.current_timestamp(),
        nullable=False,
    ),
    info={"bind_key": "ingest"},
)

track_foreignid = Table(
    "track_foreignid",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("track_id", Integer, ForeignKey("track.id"), nullable=False),
    Column(
        "foreignid_id", Integer, ForeignKey("foreignid.id"), nullable=False, index=True
    ),
    Column(
        "created",
        DateTime(timezone=True),
        server_default=sql.func.current_timestamp(),
        nullable=False,
    ),
    Column("updated", DateTime(timezone=True)),
    Column("submission_count", Integer, nullable=False),
    Index("track_foreignid_idx_uniq", "track_id", "foreignid_id", unique=True),
    info={"bind_key": "fingerprint"},
)

track_foreignid_source = Table(
    "track_foreignid_source",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("track_foreignid_id", Integer, nullable=False),
    Column("submission_id", Integer, nullable=False),
    Column("source_id", Integer, nullable=False),
    Column(
        "created",
        DateTime(timezone=True),
        server_default=sql.func.current_timestamp(),
        nullable=False,
    ),
    info={"bind_key": "ingest"},
)

meta_gid_backfill_status = Table(
    "meta_gid_backfill_status",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("last_meta_id", Integer, nullable=False),
    info={"bind_key": "fingerprint"},
)

import mbdata.models  # noqa: E402

mb_area = mbdata.models.Area.__table__
mb_artist_credit = mbdata.models.ArtistCredit.__table__
mb_artist_credit_name = mbdata.models.ArtistCreditName.__table__
mb_artist = mbdata.models.Artist.__table__
mb_iso_3166_1 = mbdata.models.ISO31661.__table__
mb_medium_format = mbdata.models.MediumFormat.__table__
mb_medium = mbdata.models.Medium.__table__
mb_recording_gid_redirect = mbdata.models.RecordingGIDRedirect.__table__
mb_isrc = mbdata.models.ISRC.__table__
mb_recording = mbdata.models.Recording.__table__
mb_release_group = mbdata.models.ReleaseGroup.__table__
mb_release_group_primary_type = mbdata.models.ReleaseGroupPrimaryType.__table__
mb_release_group_secondary_type_join = (
    mbdata.models.ReleaseGroupSecondaryTypeJoin.__table__
)
mb_release_group_secondary_type = mbdata.models.ReleaseGroupSecondaryType.__table__
mb_release = mbdata.models.Release.__table__
mb_track = mbdata.models.Track.__table__

mb_replication_control = mbdata.models.ReplicationControl.__table__

# XXX either stop using this or define view models in mbdata
mb_release_country = Table(
    "release_event",
    metadata,
    Column("release", Integer, ForeignKey("musicbrainz.release.id")),
    Column("country", Integer, ForeignKey("musicbrainz.area.id")),
    Column("date_year", Integer),
    Column("date_month", Integer),
    Column("date_day", Integer),
    schema="musicbrainz",
    info={"bind_key": "musicbrainz"},
)

for table in metadata.sorted_tables:
    if table.schema in {
        "musicbrainz",
        "cover_art_archive",
        "event_art_archive",
        "wikidocs",
        "statistics",
        "documentation",
    }:
        table.info["bind_key"] = "musicbrainz"  # type: ignore
