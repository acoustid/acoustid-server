import asyncio
import logging
from contextlib import AsyncExitStack

import asyncpg
import click
from acoustid_ext.fingerprint import (
    compute_simhash,
    decode_postgres_array,
    encode_legacy_fingerprint,
)

from acoustid.fingerprint import compute_fingerprint_gid

logger = logging.getLogger(__name__)


async def populate_fingerprint_data(postgres_url: str) -> None:
    async with AsyncExitStack() as exit_stack:
        conn = await asyncpg.connect(postgres_url)
        exit_stack.push_async_callback(conn.close)

        min_fingerprint_id = (
            await conn.fetchval("SELECT MIN(id) FROM fingerprints") or 0
        )
        max_fingerprint_id = (
            await conn.fetchval("SELECT MAX(id) FROM fingerprints") or 0
        )

        max_fingerprint_data_id = (
            await conn.fetchval("SELECT MAX(id) FROM fingerprint_data") or 0
        )

        # Start from the last processed ID + 1
        min_id = max(min_fingerprint_id, max_fingerprint_data_id + 1)
        max_id = max_fingerprint_id - 1000

        # Early return if there's nothing to process
        if min_id >= max_id:
            logger.info("No new fingerprints to process")
            return

        async def wait_for_insert_task(task: asyncio.Task | None) -> None:
            if task is not None:
                await task

        insert_task: asyncio.Task | None = None
        exit_stack.push_async_callback(wait_for_insert_task, insert_task)

        batch_size = 10000
        for i in range(min_id, max_id, batch_size):
            fingerprints = await conn.fetch(
                "SELECT id, fingerprint::text FROM fingerprints WHERE id >= $1 AND id < $2",
                i,
                min(i + batch_size, max_id),
            )
            batch = []
            for id, hashes_str in fingerprints:
                hashes = decode_postgres_array(hashes_str)
                encoded_fingerprint = encode_legacy_fingerprint(
                    hashes, 1, base64=False, signed=True
                )
                gid = compute_fingerprint_gid(1, hashes)
                simhash = compute_simhash(hashes)
                batch.append((id, gid, encoded_fingerprint, simhash))

            if insert_task is not None:
                await insert_task
                insert_task = None

            logger.info(
                "Processing batch %s to %s",
                i,
                min(i + batch_size, max_id),
            )

            insert_task = asyncio.create_task(
                conn.executemany(
                    "INSERT INTO fingerprint_data (id, gid, fingerprint, simhash) VALUES ($1, $2, $3, $4)",
                    batch,
                )
            )


@click.command()
@click.option(
    "--postgres-url",
    default="postgresql://acoustid:acoustid@localhost:5432/acoustid_fingerprint",
)
def main(postgres_url: str) -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(populate_fingerprint_data(postgres_url))


if __name__ == "__main__":
    main()
