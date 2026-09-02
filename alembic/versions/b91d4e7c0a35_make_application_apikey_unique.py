"""make application.apikey unique

application.apikey is a client credential, and lookup_application_id_by_apikey
selects by it and ends in .scalar(), which takes the first row and discards
any others silently.  The code has always assumed the column is unique --
tables.py declares application_idx_apikey as unique, and account.apikey has
the equivalent index -- but production never had it.  It has three non-unique
indexes on the column instead and no unique one, so two applications sharing
an apikey would authenticate as whichever row the index happened to return,
with no error and nothing in the logs.

There are no duplicates today: 24,689 applications, 24,689 distinct apikeys,
no nulls.  So this closes a latent gap rather than fixing live damage, and it
needs no cleanup first.

idx_application_apikey goes at the same time because the new index fully
subsumes it -- a unique btree on (apikey) serves every query a plain btree on
(apikey) does.  The unique index is created before the old one is dropped, so
there is no window without an index on the column.

Left alone deliberately: idx_application_apikey_active on (apikey, active)
and idx_application_apikey_active_true on (apikey) WHERE active IS TRUE.
Those are different shapes serving the only_active lookup path and want
separate judgement, not a drive-by drop.

Both statements are conditional, so this is a no-op on a database built from
the migration chain, where the initial migration already creates
application_idx_apikey as unique and idx_application_apikey has never existed.

Revision ID: b91d4e7c0a35
Revises: 2ec9404e8f6c
Create Date: 2026-09-02 16:00:00.000000

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "b91d4e7c0a35"
down_revision = "2ec9404e8f6c"
branch_labels = None
depends_on = None


def upgrade(engine_name):
    globals()["upgrade_%s" % engine_name]()


def downgrade(engine_name):
    globals()["downgrade_%s" % engine_name]()


def upgrade_fingerprint():
    pass


def downgrade_fingerprint():
    pass


def upgrade_ingest():
    pass


def downgrade_ingest():
    pass


def upgrade_app():
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS application_idx_apikey"
        " ON application (apikey)"
    )
    op.execute("DROP INDEX IF EXISTS idx_application_apikey")


def downgrade_app():
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_application_apikey ON application (apikey)"
    )
    op.execute("DROP INDEX IF EXISTS application_idx_apikey")
