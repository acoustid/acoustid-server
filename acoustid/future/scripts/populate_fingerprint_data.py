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


async def populate_fingerprint_data(
    postgres_url: str, min_id: int, max_id: int
) -> None:
    async with AsyncExitStack() as exit_stack:
        conn = await asyncpg.connect(postgres_url)
        exit_stack.push_async_callback(conn.close)

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
@click.option("--min-id", type=int, required=True)
@click.option("--max-id", type=int, required=True)
def main(postgres_url: str, min_id: int, max_id: int) -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(populate_fingerprint_data(postgres_url, min_id, max_id))


if __name__ == "__main__":
    main()
