import asyncio
import json

# import nats
import logging
import signal
from contextlib import AsyncExitStack

import asyncpg
import click
from acoustid_ext.fingerprint import decode_postgres_array

logger = logging.getLogger(__name__)


SLOT_NAME = "fpindex"
STREAM_NAME = "fpindex"
REPL_BATCH_SIZE = 1000
REPL_MIN_DELAY = 0.05
REPL_MAX_DELAY = 1.0


def parse_pgarray(value: str) -> list[str]:
    return [x.strip() for x in value.strip("{}").split(",")]


async def create_replication_slot(conn: asyncpg.Connection) -> tuple[bool, str | None]:
    slot_exists = await conn.fetchval(
        """
        SELECT COUNT(*) > 0
        FROM pg_replication_slots
        WHERE slot_name = $1
        """,
        SLOT_NAME,
    )

    if slot_exists:
        logger.info("Replication slot %s already exists", SLOT_NAME)
        return False, None

    logger.info("Creating snapshot")
    snapshot_id = await conn.fetchval("SELECT pg_export_snapshot()")

    logger.info("Creating replication slot %s", SLOT_NAME)
    await conn.execute(
        """
            SELECT * FROM pg_create_logical_replication_slot($1, 'wal2json', temporary => true)
        """,
        SLOT_NAME,
    )
    return True, snapshot_id


async def drop_replication_slot(conn: asyncpg.Connection) -> None:
    logger.info("Dropping replication slot %s", SLOT_NAME)
    await conn.execute(
        "SELECT * FROM pg_drop_replication_slot($1)",
        SLOT_NAME,
    )


async def load_initial_data(
    conn: asyncpg.Connection, shutdown_event: asyncio.Event
) -> None:
    """Load initial fingerprint data using a consistent snapshot"""

    async with AsyncExitStack() as exit_stack:
        await exit_stack.enter_async_context(
            conn.transaction(isolation="repeatable_read", readonly=True)
        )

        needs_import, _ = await create_replication_slot(conn)
        if not needs_import:
            return

        async def drop_replication_slot_on_error(*exc_details) -> None:
            if exc_details[0] is not None:
                await drop_replication_slot(conn)

        exit_stack.push_async_exit(drop_replication_slot_on_error)

        total_count = await conn.fetchval(
            """
            SELECT reltuples::bigint AS estimate
            FROM pg_class
            WHERE relname = 'fingerprint'
            """
        )
        logger.info("Found approximately %s fingerprints", total_count)

        cursor = conn.cursor(
            """
            SELECT id, fingerprint::text
            FROM fingerprint
            """
        )
        loaded_count = 0
        async for fp_id, fp_hashes_str in cursor:
            fp_hashes = decode_postgres_array(fp_hashes_str)
            logger.info("UPSERT %s: %s", fp_id, fp_hashes)
            loaded_count += 1
            if loaded_count % 1000 == 0:
                logger.info(
                    "Processed %d/%d fingerprints (%.2f%%)",
                    loaded_count,
                    total_count,
                    (loaded_count / total_count * 100),
                )
                if shutdown_event.is_set():
                    logger.info("Interrupting initial data load due to shutdown event")
                    raise ShutdownError

    logger.info(f"Initial data load complete. Processed {loaded_count} fingerprints.")


class ShutdownError(Exception):
    pass


def shutdown(event: asyncio.Event) -> None:
    logger.info("Shutting down...")
    event.set()


async def replicate_from_pg() -> None:
    async with AsyncExitStack() as exit_stack:
        shutdown_event = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, shutdown, shutdown_event)

        pgc = await asyncpg.connect(
            "postgresql://acoustid:acoustid@localhost:5432/acoustid_fingerprint"
        )
        exit_stack.push_async_callback(pgc.close)

        # nc = await nats.connect("nats://localhost:4222")
        # exit_stack.push_async_callback(nc.close)

        # js = nc.jetstream()

        # stream_info = await js.add_stream(name=STREAM_NAME, subjects=["fingerprints.*"])
        # logger.info("Stream info: %r", stream_info)

        try:
            await load_initial_data(pgc, shutdown_event)
        except ShutdownError:
            return

        delay = REPL_MIN_DELAY

        while not shutdown_event.is_set():
            changes = await pgc.fetch(
                "SELECT lsn, xid, data FROM pg_logical_slot_peek_changes($1, NULL, $2, 'add-tables', 'public.fingerprint', 'format-version', '2')",
                SLOT_NAME,
                REPL_BATCH_SIZE,
            )

            logger.info("Got %d changes", len(changes))

            last_processed_lsn: str | None = None
            for lsn, xid, data_json in changes:
                data = json.loads(data_json)
                logger.info("LSN: %s, XID: %s, data: %s", lsn, xid, data)

                if data["action"] not in {"I", "U", "D"}:
                    last_processed_lsn = lsn
                    continue

                if data["schema"] == "public" and data["table"] == "fingerprint":

                    if data["action"] == "I":
                        for col in data["columns"]:
                            if col["name"] == "id":
                                fp_id = col["value"]
                                break
                        else:
                            raise ValueError("No fingerprint id found")

                        for col in data["columns"]:
                            if col["name"] == "fingerprint":
                                fp_hashes = decode_postgres_array(col["value"])
                                break
                        else:
                            raise ValueError("No fingerprint data found")

                        logger.info("UPSERT %s: %s", fp_id, fp_hashes)

                    elif data["action"] == "U":
                        for col in data["identity"]:
                            if col["name"] == "id":
                                fp_id = col["value"]
                                break
                        else:
                            raise ValueError("No fingerprint id found")

                        for col in data["columns"]:
                            if col["name"] == "fingerprint":
                                fp_hashes = decode_postgres_array(col["value"])
                                break
                        else:
                            raise ValueError("No fingerprint data found")
                        logger.info("UPSERT %s: %s", fp_id, fp_hashes)

                    elif data["action"] == "D":
                        for col in data["identity"]:
                            if col["name"] == "id":
                                fp_id = col["value"]
                                break
                        else:
                            raise ValueError("No fingerprint id found")
                        logger.info("DELETE %s", fp_id)

                last_processed_lsn = lsn

            if last_processed_lsn is not None:
                await pgc.execute(
                    "SELECT pg_replication_slot_advance($1, $2)",
                    SLOT_NAME,
                    last_processed_lsn,
                )
                delay = REPL_MIN_DELAY
            else:
                delay = min(delay * 2, REPL_MAX_DELAY)

            # if we processed less than the full batch size, wait a bit
            if len(changes) < REPL_BATCH_SIZE:
                logger.info("Waiting %s seconds", delay)
                try:
                    await asyncio.wait_for(shutdown_event.wait(), delay)
                except asyncio.TimeoutError:
                    pass


@click.group()
def main() -> None:
    logging.basicConfig(level=logging.INFO)


@main.command("replicate-from-pg")
def replicate_from_pg_cmd() -> None:
    asyncio.run(replicate_from_pg())


if __name__ == "__main__":
    main()
