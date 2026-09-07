import importlib
import os
from typing import Optional

import click
from sqlalchemy import sql

from acoustid.cron import run_cron
from acoustid.export import run_export
from acoustid.future.fpindex.feed import DEFAULT_PORT, run_feed_app
from acoustid.script import Script
from acoustid.scripts.backfill_singleton_gids import (
    DEFAULT_BATCH_SIZE as SINGLETON_BATCH_SIZE,
)
from acoustid.scripts.backfill_singleton_gids import (
    DUPS_TABLE,
)
from acoustid.scripts.backfill_singleton_gids import GID_TABLE as SINGLETON_GID_TABLE
from acoustid.scripts.backfill_singleton_gids import (
    PROGRESS_TABLE as SINGLETON_PROGRESS,
)
from acoustid.scripts.backfill_singleton_gids import (
    drop_progress,
    init_progress,
    report,
    run_backfill_singleton_gids,
)
from acoustid.scripts.backfill_submission_result import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_RANGE_SIZE,
    GID_TABLE,
    PROGRESS_TABLE,
    drop_queue,
    init_queue,
    requeue_stale,
    run_backfill,
    run_validate,
    watershed,
)
from acoustid.scripts.claim_duplicate_gids import DEFAULT_BATCH_SIZE as CLAIM_BATCH_SIZE
from acoustid.scripts.claim_duplicate_gids import DUPS_TABLE as CLAIM_DUPS_TABLE
from acoustid.scripts.claim_duplicate_gids import PROGRESS_TABLE as CLAIM_PROGRESS
from acoustid.scripts.claim_duplicate_gids import drop_progress as claim_drop_progress
from acoustid.scripts.claim_duplicate_gids import init_progress as claim_init_progress
from acoustid.scripts.claim_duplicate_gids import report as claim_report
from acoustid.scripts.claim_duplicate_gids import run_claim
from acoustid.scripts.import_submissions import run_import
from acoustid.worker import run_worker
from acoustid.wsgi_utils import run_api_app, run_web_app


@click.group()
def cli():
    # type: () -> None
    pass


@cli.group()
def run():
    # type: () -> None
    pass


@run.command("web")
@click.option("-c", "--config", default="acoustid.conf", envvar="ACOUSTID_CONFIG")
@click.option("-w", "--workers", type=int)
@click.option("-t", "--threads", type=int)
def run_web_cmd(config, workers=None, threads=None):
    # type: (str, Optional[int], Optional[int]) -> None
    """Run production uWSGI with the website."""
    os.environ["ACOUSTID_CONFIG"] = config
    script = Script(config)
    script.setup_console_logging()
    run_web_app(script.config, workers=workers, threads=threads)


@run.command("api")
@click.option("-c", "--config", default="acoustid.conf", envvar="ACOUSTID_CONFIG")
@click.option("-w", "--workers", type=int)
@click.option("-t", "--threads", type=int)
def run_api_cmd(config, workers=None, threads=None):
    # type: (str, Optional[int], Optional[int]) -> None
    """Run production uWSGI with the API."""
    os.environ["ACOUSTID_CONFIG"] = config
    script = Script(config)
    script.setup_console_logging()
    run_api_app(script.config, workers=workers, threads=threads)


@run.command("fpindex-feed")
@click.option("-c", "--config", default="acoustid.conf", envvar="ACOUSTID_CONFIG")
@click.option("-h", "--host", default="0.0.0.0")
@click.option("-p", "--port", type=int, default=DEFAULT_PORT)
@click.option("-w", "--workers", type=int)
def run_fpindex_feed_cmd(
    config: str, host: str, port: int, workers: Optional[int]
) -> None:
    """Run the changelog feed that fpindex nodes replicate from."""
    # Set for the benefit of the uvicorn factory, which is re-imported in each
    # worker process and so cannot be handed the path directly.
    os.environ["ACOUSTID_CONFIG"] = config
    script = Script(config)
    script.setup_console_logging()
    run_feed_app(host=host, port=port, workers=workers)


@run.command("cron")
@click.option("-c", "--config", default="acoustid.conf", envvar="ACOUSTID_CONFIG")
def run_cron_cmd(config: str) -> None:
    """Run cron."""
    script = Script(config)
    script.setup_console_logging()
    run_cron(script)


@run.command("worker")
@click.option("-c", "--config", default="acoustid.conf", envvar="ACOUSTID_CONFIG")
def run_worker_cmd(config: str) -> None:
    """Run worker."""
    script = Script(config)
    script.setup_console_logging()
    run_worker(script)


@run.command("import")
@click.option("-c", "--config", default="acoustid.conf", envvar="ACOUSTID_CONFIG")
def run_import_cmd(config):
    # type: (str) -> None
    """Run import."""
    script = Script(config)
    script.setup_console_logging(verbose=True)
    run_import(script)


@run.command("script")
@click.argument("name")
@click.option("-c", "--config", default="acoustid.conf", envvar="ACOUSTID_CONFIG")
def run_script_cmd(name, config):
    # type: (str, str) -> None
    """Run a built-in script."""
    script = Script(config)
    script.setup_console_logging()
    mod = importlib.import_module("acoustid.scripts.{}".format(name))
    func_name = "run_{}".format(name)
    func = getattr(mod, func_name)
    func(script, None, None)


@cli.group()
def data():
    # type: () -> None
    """Commands for working with the public data files."""


@data.command("export")
@click.option("-c", "--config", default="acoustid.conf", envvar="ACOUSTID_CONFIG")
@click.option(
    "-d",
    "--directory",
    help="Directory to write the export files into.",
)
@click.option(
    "--max-days",
    type=int,
    help="How many past days to export. Only complete days are exported, so "
    "this is a window ending at midnight today.",
)
def data_export_cmd(
    config: str, directory: Optional[str], max_days: Optional[int]
) -> None:
    """Export the daily data files published at data.acoustid.org.

    Runs are idempotent -- a file that is already there is left alone -- so
    this is safe to run on a schedule, and re-running it with a larger
    --max-days is how a gap in the published files gets backfilled.
    """
    script = Script(config)
    script.setup_console_logging()
    script.setup_sentry(component="export")

    if directory is None:
        directory = script.config.export.directory
    if not directory:
        raise click.UsageError(
            "No export directory configured, use --directory or "
            "ACOUSTID_EXPORT_DIRECTORY."
        )
    if max_days is None:
        max_days = script.config.export.max_days

    bind_key = script.config.databases.read_only_bind_key("fingerprint")
    run_export(script.db_engines[bind_key], directory, max_days=max_days)


@cli.group("backfill-submission-result")
def backfill_submission_result():
    # type: () -> None
    """Reconstruct submission_result rows for submissions predating the table."""


@backfill_submission_result.command("validate")
@click.option("-c", "--config", default="acoustid.conf", envvar="ACOUSTID_CONFIG")
@click.option(
    "--lo", type=int, default=None, help="First submission id (default: the watershed)."
)
@click.option("--hi", type=int, default=None, help="Last submission id, exclusive.")
@click.option("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
@click.option("--gid-table", default=GID_TABLE)
def backfill_validate_cmd(config, lo, hi, batch_size, gid_table):
    # type: (str, Optional[int], Optional[int], int, str) -> None
    """Diff reconstructed rows against the native ones. Writes nothing."""
    script = Script(config)
    script.setup_console_logging()
    with script.context() as ctx:
        ingest_db = ctx.db.get_ingest_db(read_only=True)
        start = lo if lo is not None else watershed(ingest_db)
        if start is None:
            raise click.ClickException("submission_result is empty, nothing to compare")
        end = hi
        if end is None:
            end = ingest_db.execute(
                sql.text("SELECT max(submission_id) + 1 FROM submission_result")
            ).scalar()
        if end is None:
            raise click.ClickException("submission_result is empty, nothing to compare")
    run_validate(script, start, end, batch_size=batch_size, gid_table=gid_table)


@backfill_submission_result.command("init")
@click.option("-c", "--config", default="acoustid.conf", envvar="ACOUSTID_CONFIG")
@click.option("--lo", type=int, default=1, help="First submission id.")
@click.option(
    "--hi",
    type=int,
    default=None,
    help=(
        "Last submission id, exclusive. Defaults to the watershed, which keeps"
        " every written row below the range that has native rows, so the whole"
        " backfill stays deletable in one statement."
    ),
)
@click.option("--range-size", type=int, default=DEFAULT_RANGE_SIZE)
def backfill_init_cmd(config, lo, hi, range_size):
    # type: (str, int, Optional[int], int) -> None
    """Create the work queue and fill it with ranges."""
    script = Script(config)
    script.setup_console_logging()
    with script.context() as ctx:
        ingest_db = ctx.db.get_ingest_db()
        end = hi if hi is not None else watershed(ingest_db)
        if end is None:
            raise click.ClickException("submission_result is empty, pass --hi")
        count = init_queue(ingest_db, lo, end, range_size)
        ctx.db.session.commit()
    click.echo("%d ranges queued, %d..%d" % (count, lo, end))


@backfill_submission_result.command("run")
@click.option("-c", "--config", default="acoustid.conf", envvar="ACOUSTID_CONFIG")
@click.option("--worker", default=None, help="Worker name recorded on claimed ranges.")
@click.option("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
@click.option("--gid-table", default=GID_TABLE)
@click.option(
    "--max-ranges",
    type=int,
    default=None,
    help="Stop after this many ranges, between ranges. Use 1 for a first pass.",
)
def backfill_run_cmd(config, worker, batch_size, gid_table, max_ranges):
    # type: (str, Optional[str], int, str, Optional[int]) -> None
    """Claim ranges from the queue and write them, lowest ids first."""
    script = Script(config)
    script.setup_console_logging()
    name = worker or "%s-%d" % (os.uname().nodename, os.getpid())
    run_backfill(
        script,
        name,
        batch_size=batch_size,
        gid_table=gid_table,
        max_ranges=max_ranges,
    )


@backfill_submission_result.command("requeue")
@click.option("-c", "--config", default="acoustid.conf", envvar="ACOUSTID_CONFIG")
@click.option(
    "--older-than", default="6 hours", help="Claim age to consider abandoned."
)
def backfill_requeue_cmd(config, older_than):
    # type: (str, str) -> None
    """Return ranges claimed by dead workers to the queue."""
    script = Script(config)
    script.setup_console_logging()
    with script.context() as ctx:
        count = requeue_stale(ctx.db.get_ingest_db(), older_than)
        ctx.db.session.commit()
    click.echo("%d ranges requeued" % (count,))


@backfill_submission_result.command("drop")
@click.option("-c", "--config", default="acoustid.conf", envvar="ACOUSTID_CONFIG")
def backfill_drop_cmd(config):
    # type: (str) -> None
    """Remove the work queue once the backfill is finished."""
    script = Script(config)
    script.setup_console_logging()
    with script.context() as ctx:
        drop_queue(ctx.db.get_ingest_db())
        ctx.db.session.commit()
    click.echo("dropped %s" % (PROGRESS_TABLE,))


@cli.group("backfill-singleton-gids")
def backfill_singleton_gids():
    # type: () -> None
    """Give a gid to every meta row whose content is unique."""


@backfill_singleton_gids.command("init")
@click.option("-c", "--config", default="acoustid.conf", envvar="ACOUSTID_CONFIG")
def singleton_gids_init_cmd(config):
    # type: (str) -> None
    """Create the progress table."""
    script = Script(config)
    script.setup_console_logging()
    with script.context() as ctx:
        init_progress(ctx.db.get_fingerprint_db())
        ctx.db.session.commit()
    click.echo("created %s" % (SINGLETON_PROGRESS,))


@backfill_singleton_gids.command("run")
@click.option("-c", "--config", default="acoustid.conf", envvar="ACOUSTID_CONFIG")
@click.option(
    "--batch-size",
    type=int,
    default=SINGLETON_BATCH_SIZE,
    help="meta ids per transaction, not rows updated.",
)
@click.option(
    "--limit",
    type=int,
    default=None,
    help="Stop after this many batches. Use it for a first pass.",
)
@click.option("--gid-table", default=SINGLETON_GID_TABLE)
@click.option("--dups-table", default=DUPS_TABLE)
def singleton_gids_run_cmd(config, batch_size, limit, gid_table, dups_table):
    # type: (str, int, Optional[int], str, str) -> None
    """Fill in gids from the cursor onwards."""
    script = Script(config)
    script.setup_console_logging()
    run_backfill_singleton_gids(
        script,
        batch_size=batch_size,
        limit=limit,
        gid_table=gid_table,
        dups_table=dups_table,
    )


@backfill_singleton_gids.command("report")
@click.option("-c", "--config", default="acoustid.conf", envvar="ACOUSTID_CONFIG")
@click.option("--gid-table", default=SINGLETON_GID_TABLE)
@click.option("--dups-table", default=DUPS_TABLE)
def singleton_gids_report_cmd(config, gid_table, dups_table):
    # type: (str, str, str) -> None
    """Count singletons still without a gid, and how many are blocked."""
    script = Script(config)
    script.setup_console_logging()
    with script.context() as ctx:
        remaining, blocked = report(ctx.db.get_fingerprint_db(), gid_table, dups_table)
    click.echo("%d singletons still without a gid" % (remaining,))
    click.echo("%d of those blocked by a row that already holds it" % (blocked,))


@backfill_singleton_gids.command("drop")
@click.option("-c", "--config", default="acoustid.conf", envvar="ACOUSTID_CONFIG")
def singleton_gids_drop_cmd(config):
    # type: (str) -> None
    """Remove the progress table once the backfill is finished."""
    script = Script(config)
    script.setup_console_logging()
    with script.context() as ctx:
        drop_progress(ctx.db.get_fingerprint_db())
        ctx.db.session.commit()
    click.echo("dropped %s" % (SINGLETON_PROGRESS,))


@cli.group("claim-duplicate-gids")
def claim_duplicate_gids():
    # type: () -> None
    """Give each duplicate group's gid to one of its members."""


@claim_duplicate_gids.command("init")
@click.option("-c", "--config", default="acoustid.conf", envvar="ACOUSTID_CONFIG")
def claim_gids_init_cmd(config):
    # type: (str) -> None
    """Create the progress table."""
    script = Script(config)
    script.setup_console_logging()
    with script.context() as ctx:
        claim_init_progress(ctx.db.get_fingerprint_db())
        ctx.db.session.commit()
    click.echo("created %s" % (CLAIM_PROGRESS,))


@claim_duplicate_gids.command("run")
@click.option("-c", "--config", default="acoustid.conf", envvar="ACOUSTID_CONFIG")
@click.option(
    "--batch-size",
    type=click.IntRange(min=1),
    default=CLAIM_BATCH_SIZE,
    help="Groups per transaction. Each claims at most one row.",
)
@click.option(
    "--limit",
    type=click.IntRange(min=0),
    default=None,
    help="Stop after this many batches. Use it for a first pass.",
)
@click.option("--dups-table", default=CLAIM_DUPS_TABLE)
def claim_gids_run_cmd(config, batch_size, limit, dups_table):
    # type: (str, int, Optional[int], str) -> None
    """Claim gids from the cursor onwards."""
    script = Script(config)
    script.setup_console_logging()
    run_claim(script, batch_size=batch_size, limit=limit, dups_table=dups_table)


@claim_duplicate_gids.command("report")
@click.option("-c", "--config", default="acoustid.conf", envvar="ACOUSTID_CONFIG")
@click.option("--dups-table", default=CLAIM_DUPS_TABLE)
def claim_gids_report_cmd(config, dups_table):
    # type: (str, str) -> None
    """Count groups whose gid is held, and groups where it is not."""
    script = Script(config)
    script.setup_console_logging()
    with script.context() as ctx:
        claimed, unclaimed = claim_report(ctx.db.get_fingerprint_db(), dups_table)
    click.echo("%d groups have a member holding the gid" % (claimed,))
    click.echo("%d groups do not" % (unclaimed,))


@claim_duplicate_gids.command("drop")
@click.option("-c", "--config", default="acoustid.conf", envvar="ACOUSTID_CONFIG")
def claim_gids_drop_cmd(config):
    # type: (str) -> None
    """Remove the progress table once the claim is finished."""
    script = Script(config)
    script.setup_console_logging()
    with script.context() as ctx:
        claim_drop_progress(ctx.db.get_fingerprint_db())
        ctx.db.session.commit()
    click.echo("dropped %s" % (CLAIM_PROGRESS,))


@cli.command("shell")
@click.option("-c", "--config", default="acoustid.conf", envvar="ACOUSTID_CONFIG")
def shell_cmd(config):
    # type: (str) -> None
    """Run shell."""
    import IPython

    script = Script(config)
    script.setup_console_logging()
    with script.context() as ctx:
        _ = ctx
        IPython.embed()


def main():
    # type: () -> None
    cli()
