"""add fpindex_changelog

Revision ID: a1f4c72b90de
Revises: 8953fd9f151a
Create Date: 2026-07-29 16:20:00.000000

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "a1f4c72b90de"
down_revision = "8953fd9f151a"
branch_labels = None
depends_on = None


# Must match acoustid.tables.FPINDEX_CHANGELOG_LOCK_KEY. Migrations cannot
# import the models -- they have to keep working as those move -- so the value
# is repeated here on purpose. Changing it in one place only would leave two
# different locks and silently stop serialising writers.
LOCK_KEY = 7723016524936704001

# Must match acoustid.tables.FPINDEX_CHANGELOG_CREATE_AHEAD_MONTHS, for the same
# reason and with the same caveat about not importing it. Drift here is benign
# next to the lock key: the hourly task tops the runway back up, and headroom is
# alerted on regardless.
CREATE_AHEAD_MONTHS = 12


def upgrade(engine_name):
    globals()["upgrade_%s" % engine_name]()


def downgrade(engine_name):
    globals()["downgrade_%s" % engine_name]()


def upgrade_app():
    pass


def downgrade_app():
    pass


def upgrade_ingest():
    pass


def downgrade_ingest():
    pass


def upgrade_fingerprint():
    op.execute("CREATE SEQUENCE fpindex_changelog_id_seq AS bigint")
    op.execute(
        """
        CREATE TABLE fpindex_changelog (
            id bigint NOT NULL DEFAULT nextval('fpindex_changelog_id_seq'),
            fingerprint_id integer NOT NULL,
            query integer[] NOT NULL,
            xid xid8 NOT NULL DEFAULT pg_current_xact_id(),
            created timestamp with time zone NOT NULL DEFAULT clock_timestamp(),
            CONSTRAINT fpindex_changelog_pkey PRIMARY KEY (id, created)
        ) PARTITION BY RANGE (created)
        """
    )
    op.execute("ALTER SEQUENCE fpindex_changelog_id_seq OWNED BY fpindex_changelog.id")

    # The current month plus a year of runway, created here rather than left to
    # the hourly maintenance task.
    #
    # This has to happen in the same transaction as the trigger below. There is
    # no DEFAULT partition -- see acoustid.tables for that argument -- so the
    # moment the trigger exists, a fingerprint insert with no partition to land
    # in fails. Waiting for the first cron run would leave that window open.
    #
    # Done in plpgsql, on the server, so the months come from the database's own
    # calendar and timezone. That is the same calendar the maintenance task uses
    # (`SELECT current_date`) and the same one the partition key is compared
    # against, so the two cannot disagree about where a month begins. Keep the
    # naming in step with acoustid.tables.fpindex_changelog_partition_name: the
    # maintenance task recognises partitions by that pattern and ignores
    # anything else, so a mismatch here would leave it reporting no headroom.
    op.execute(
        f"""
        DO $$
        DECLARE
            start_month date := date_trunc('month', current_date)::date;
            part_month date;
            offset_months int;
        BEGIN
            FOR offset_months IN 0..{CREATE_AHEAD_MONTHS} LOOP
                part_month := (
                    start_month + (offset_months || ' months')::interval
                )::date;
                EXECUTE format(
                    'CREATE TABLE %I PARTITION OF fpindex_changelog '
                    'FOR VALUES FROM (%L) TO (%L)',
                    'fpindex_changelog_' || to_char(part_month, 'YYYYMM'),
                    part_month,
                    (part_month + interval '1 month')::date
                );
            END LOOP;
        END
        $$
        """
    )

    # The advisory lock is taken here, inside the trigger, rather than being
    # documented as something callers must do. A requirement in prose is what
    # produced the gaps in the old updater; taken here it covers every writer
    # and cannot be forgotten. It is acquired before the changelog id is
    # allocated and released at commit, so lock order == id order == commit
    # order, which is what makes `WHERE id > cursor` safe for consumers.
    #
    # AFTER INSERT only. Not UPDATE: inc_fingerprint_submission_count updates
    # submission_count on every duplicate submission and the fingerprint array
    # itself never changes, so an UPDATE arm would be pure noise. Not DELETE:
    # fingerprints are never deleted.
    op.execute(
        f"""
        CREATE FUNCTION fpindex_changelog_insert() RETURNS trigger AS $$
        BEGIN
            PERFORM pg_advisory_xact_lock({LOCK_KEY});
            INSERT INTO fpindex_changelog (fingerprint_id, query)
                VALUES (NEW.id, acoustid_extract_query(NEW.fingerprint));
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER fingerprint_fpindex_changelog
            AFTER INSERT ON fingerprint
            FOR EACH ROW
            EXECUTE FUNCTION fpindex_changelog_insert()
        """
    )

    # What retention threw away. Left empty on purpose: no row means nothing has
    # ever been deleted, which is the truth on a fresh install, and it saves
    # seeding the same row from both here and create_all. Retention upserts it.
    op.execute(
        """
        CREATE TABLE fpindex_meta (
            singleton boolean NOT NULL DEFAULT true,
            last_deleted_id bigint NOT NULL,
            last_deleted_created timestamp with time zone NOT NULL,
            last_deleted_xid xid8 NOT NULL,
            updated timestamp with time zone NOT NULL DEFAULT clock_timestamp(),
            CONSTRAINT fpindex_meta_pkey PRIMARY KEY (singleton),
            CONSTRAINT fpindex_meta_singleton CHECK (singleton)
        )
        """
    )


def downgrade_fingerprint():
    op.execute("DROP TRIGGER IF EXISTS fingerprint_fpindex_changelog ON fingerprint")
    op.execute("DROP FUNCTION IF EXISTS fpindex_changelog_insert()")
    op.execute("DROP TABLE IF EXISTS fpindex_meta")
    op.execute("DROP TABLE IF EXISTS fpindex_changelog")
    op.execute("DROP SEQUENCE IF EXISTS fpindex_changelog_id_seq")
