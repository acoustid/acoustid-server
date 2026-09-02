"""catch up the gid-era schema that was applied by hand

meta.gid, meta_id_history and submission_result.meta_gid were added to
production directly in 2020 and never migrated, so `alembic upgrade head`
built a database missing all three.  meta_created_idx is here for the same
reason: d2176bc400c8 added meta.created without an index and the index was
put on production by hand afterwards.  That is not cosmetic: find_or_insert_meta
inserts into meta.gid on every metadata submission, so a server pointed at an
alembic-built database failed on the first one -- including the database the
init-db service creates.

Every statement is IF NOT EXISTS, so applying this to production changes
nothing and only stamps the revision.  The DDL is written to match the
production objects exactly; it was diffed against their \\d output before
being applied anywhere.

meta_idx_gid is declared here as a plain unique index, which is the end state
once every meta row has a gid.  Production currently carries a PARTIAL variant
of it, unique only where gid is not null, because most of the 387M rows have
no gid yet and the predicate keeps the index at 2.2 GB instead of 7.8 GB.
That is a temporary operational optimisation, not the intended schema, so it
is deliberately not declared here -- the two converge when the gid backfill
completes and production rebuilds the index without the predicate.  Until
then the conditional CREATE leaves production's index untouched.

meta_id_history has NO index on gid: its access pattern is old id -> gid,
which the primary key serves, and the dedup is about to add ~207M rows to it,
so an index nothing reads would be pure write amplification.

Revision ID: d3b8f5a21c74
Revises: b91d4e7c0a35
Create Date: 2026-09-02 14:00:00.000000

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "d3b8f5a21c74"
down_revision = "b91d4e7c0a35"
branch_labels = None
depends_on = None


def upgrade(engine_name):
    globals()["upgrade_%s" % engine_name]()


def downgrade(engine_name):
    globals()["downgrade_%s" % engine_name]()


def upgrade_app():
    pass


def downgrade_app():
    pass


def upgrade_fingerprint():
    op.execute("CREATE INDEX IF NOT EXISTS meta_created_idx ON meta (created)")
    op.execute("ALTER TABLE meta ADD COLUMN IF NOT EXISTS gid uuid")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS meta_idx_gid ON meta (gid)")
    op.execute(
        "CREATE TABLE IF NOT EXISTS meta_id_history ("
        " id integer NOT NULL,"
        " gid uuid NOT NULL,"
        " CONSTRAINT meta_id_history_pkey PRIMARY KEY (id)"
        ")"
    )


def downgrade_fingerprint():
    op.execute("DROP TABLE IF EXISTS meta_id_history")
    op.execute("DROP INDEX IF EXISTS meta_created_idx")
    op.execute("DROP INDEX IF EXISTS meta_idx_gid")
    op.execute("ALTER TABLE meta DROP COLUMN IF EXISTS gid")


def upgrade_ingest():
    op.execute("ALTER TABLE submission_result ADD COLUMN IF NOT EXISTS meta_gid uuid")


def downgrade_ingest():
    op.execute("ALTER TABLE submission_result DROP COLUMN IF EXISTS meta_gid")
