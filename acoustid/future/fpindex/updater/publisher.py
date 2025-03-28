import array
import asyncio
import json
import logging
import signal
from contextlib import AsyncExitStack

import asyncpg
import click
import msgspec
import nats
from acoustid_ext.fingerprint import (
    compute_simhash,
    decode_postgres_array,
    encode_legacy_fingerprint,
)
from nats.js.api import StreamConfig

from acoustid.future.fpindex.updater.queue import (
    STREAM_NAME,
    SUBJECT_NAME,
    FingerprintDelete,
    FingerprintInsert,
    FingerprintUpdate,
)

logger = logging.getLogger(__name__)


SLOT_NAME = "fpindex"
REPL_BATCH_SIZE = 1000
REPL_MIN_DELAY = 0.05
REPL_MAX_DELAY = 1.0


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


class FingerprintUpdateReceiver:

    async def insert(
        self, xid: int, lsn: int, fp_id: int, fp_hashes: array.array[int]
    ) -> None:
        logger.info("INSERT %s: %s", fp_id, fp_hashes)

    async def update(
        self, xid: int, lsn: int, fp_id: int, fp_hashes: array.array[int]
    ) -> None:
        logger.info("UPDATE %s: %s", fp_id, fp_hashes)

    async def delete(self, xid: int, lsn: int, fp_id: int) -> None:
        logger.info("DELETE %s", fp_id)


class NatsFingerprintUpdateReceiver(FingerprintUpdateReceiver):

    def __init__(self, nc: nats.NATS, stream_name: str):
        super().__init__()
        self.nc = nc
        self.stream_name = stream_name
        self.js = nc.jetstream()

    async def prepare(self) -> None:
        stream_info = await self.js.add_stream(
            name=self.stream_name,
            subjects=[f"{SUBJECT_NAME}.*"],
            config=StreamConfig(
                max_msgs_per_subject=1,
            ),
        )
        logger.info("Stream info: %r", stream_info)

    async def insert(
        self, xid: int, lsn: int, fp_id: int, fp_hashes: array.array[int]
    ) -> None:
        payload = FingerprintInsert(
            xid=xid,
            lsn=lsn,
            id=fp_id,
            hashes=encode_legacy_fingerprint(fp_hashes, algorithm=0, base64=False),
            simhash=compute_simhash(fp_hashes),
        )
        await self.js.publish(
            stream=self.stream_name,
            subject=f"{SUBJECT_NAME}.{fp_id}",
            payload=msgspec.msgpack.encode(payload),
        )

    async def update(
        self, xid: int, lsn: int, fp_id: int, fp_hashes: array.array[int]
    ) -> None:
        payload = FingerprintUpdate(
            xid=xid,
            lsn=lsn,
            id=fp_id,
            hashes=encode_legacy_fingerprint(fp_hashes, algorithm=0, base64=False),
            simhash=compute_simhash(fp_hashes),
        )
        await self.js.publish(
            stream=self.stream_name,
            subject=f"{SUBJECT_NAME}.{fp_id}",
            payload=msgspec.msgpack.encode(payload),
        )

    async def delete(self, xid: int, lsn: int, fp_id: int) -> None:
        payload = FingerprintDelete(
            xid=xid,
            lsn=lsn,
            id=fp_id,
        )
        await self.js.publish(
            stream=self.stream_name,
            subject=f"{SUBJECT_NAME}.{fp_id}",
            payload=msgspec.msgpack.encode(payload),
        )


async def load_initial_data(
    conn: asyncpg.Connection,
    receiver: FingerprintUpdateReceiver,
    shutdown_event: asyncio.Event,
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
            await receiver.insert(0, 0, fp_id, fp_hashes)
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

    logger.info("Initial data load complete. Processed %d fingerprints.", loaded_count)


async def replicate_data(
    conn: asyncpg.Connection,
    receiver: FingerprintUpdateReceiver,
    shutdown_event: asyncio.Event,
) -> None:
    delay = REPL_MIN_DELAY

    while True:
        if shutdown_event.is_set():
            raise ShutdownError

        changes = await conn.fetch(
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

                    await receiver.insert(xid, lsn, fp_id, fp_hashes)

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

                    await receiver.update(xid, lsn, fp_id, fp_hashes)

                elif data["action"] == "D":
                    for col in data["identity"]:
                        if col["name"] == "id":
                            fp_id = col["value"]
                            break
                    else:
                        raise ValueError("No fingerprint id found")

                    await receiver.delete(xid, lsn, fp_id)

            last_processed_lsn = lsn

        if last_processed_lsn is not None:
            await conn.execute(
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


class ShutdownError(Exception):
    pass


def shutdown(event: asyncio.Event) -> None:
    logger.info("Shutting down...")
    event.set()


async def replicate_from_pg(postgres_url: str, nats_url: str, stream_name: str) -> None:
    async with AsyncExitStack() as exit_stack:
        shutdown_event = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, shutdown, shutdown_event)

        pgc = await asyncpg.connect(postgres_url)
        exit_stack.push_async_callback(pgc.close)

        nc = await nats.connect(nats_url)
        exit_stack.push_async_callback(nc.close)

        receiver = NatsFingerprintUpdateReceiver(nc, stream_name)
        await receiver.prepare()

        try:
            await load_initial_data(pgc, receiver, shutdown_event)
            await replicate_data(pgc, receiver, shutdown_event)
        except ShutdownError:
            pass


@click.command()
@click.option(
    "--postgres-url",
    default="postgresql://acoustid:acoustid@localhost:5432/acoustid_fingerprint",
)
@click.option("--nats-url", default="nats://localhost:4222")
@click.option("--stream-name", default=STREAM_NAME)
def main(postgres_url: str, nats_url: str, stream_name: str) -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(replicate_from_pg(postgres_url, nats_url, stream_name))


if __name__ == "__main__":
    main()
