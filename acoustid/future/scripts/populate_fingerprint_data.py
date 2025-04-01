import asyncio
import logging
from contextlib import AsyncExitStack
from uuid import UUID

import asyncpg
import click
from acoustid_ext.fingerprint import (
    compute_simhash,
    decode_postgres_array,
    encode_legacy_fingerprint,
)

from acoustid.fingerprint import compute_fingerprint_gid

logger = logging.getLogger(__name__)


async def insert_data(
    conn: asyncpg.Connection, batch: list[tuple[int, UUID, bytes, int]]
) -> None:
    async with conn.transaction():
        await conn.executemany(
            "INSERT INTO fingerprint_data (id, gid, fingerprint, simhash) VALUES ($1, $2, $3, $4)",
            batch,
        )


async def populate_fingerprint_data(postgres_url: str) -> None:
    async with AsyncExitStack() as exit_stack:
        conn = await asyncpg.connect(postgres_url)
        exit_stack.push_async_callback(conn.close)

        row = await conn.fetchrow(
            """
            SELECT
                (SELECT MIN(id) FROM fingerprint) as min_fingerprint_id,
                (SELECT MAX(id) FROM fingerprint) as max_fingerprint_id,
                (SELECT MAX(id) FROM fingerprint_data) as max_fingerprint_data_id
        """
        )
        assert row is not None, "No rows returned"

        min_fingerprint_id = row["min_fingerprint_id"] or 0
        max_fingerprint_id = row["max_fingerprint_id"] or 0
        max_fingerprint_data_id = row["max_fingerprint_data_id"] or 0

        # Buffer size to avoid processing records that might still be changing
        buffer_size = 1000

        # Start from the last processed ID + 1
        min_id = max(min_fingerprint_id, max_fingerprint_data_id + 1)
        max_id = max_fingerprint_id - buffer_size

        # Early return if there's nothing to process
        if min_id >= max_id:
            logger.info("No new fingerprints to process")
            return

        batch_size = 10000
        for i in range(min_id, max_id, batch_size):
            fingerprints = await conn.fetch(
                "SELECT id, fingerprint::text FROM fingerprint WHERE id >= $1 AND id < $2",
                i,
                min(i + batch_size, max_id),
            )
            batch = []
            for id, hashes_str in fingerprints:
                hashes = decode_postgres_array(hashes_str, signed=True)
                encoded_fingerprint = encode_legacy_fingerprint(
                    hashes, 1, base64=False, signed=True
                )
                gid = compute_fingerprint_gid(1, hashes)
                simhash = compute_simhash(hashes)
                batch.append((id, gid, encoded_fingerprint, simhash))

            logger.info(
                "Processing batch %s to %s",
                i,
                min(i + batch_size, max_id),
            )

            await insert_data(conn, batch)


@click.command()
@click.option(
    "--postgres-url",
    required=True,
)
def main(postgres_url: str) -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(populate_fingerprint_data(postgres_url))


if __name__ == "__main__":
    main()
