import asyncio
import logging
from collections.abc import Iterable
from contextlib import AsyncExitStack

import click
import msgspec.msgpack
import nats
from nats.aio.msg import Msg

logger = logging.getLogger("aserver.worker")


async def handle_message(msg: Msg) -> None:
    try:
        logger.debug("Headers: %s", msg.headers)
        logger.debug("Metadata: %s", msg.metadata)
        payload = msgspec.msgpack.decode(msg.data)
        logger.debug("Payload: %s", payload)
        # TODO handle messages
        await msg.ack()
    except Exception:
        logger.exception("Error handling message")
        await msg.nak()


async def worker(
    nats_servers: list[str],
    nats_subject: str,
    nats_queue: str,
    postgres_app_dsn: str,
    postgres_fingerprint_dsn: str,
    postgres_ingest_dsn: str,
    postgres_musicbrainz_dsn: str,
) -> None:
    async with AsyncExitStack() as exit_stack:
        nc = await nats.connect(servers=nats_servers)
        exit_stack.push_async_callback(nc.close)

        # postgres_app_conn = sqlalchemy.create_async_engine(postgres_app_dsn)
        # postgres_fingerprint_conn = sqlalchemy.create_async_engine(
        #     postgres_fingerprint_dsn
        # )
        # postgres_ingest_conn = sqlalchemy.create_async_engine(postgres_ingest_dsn)
        # postgres_musicbrainz_conn = sqlalchemy.create_async_engine(
        #     postgres_musicbrainz_dsn
        # )

        logger.info(
            "Connected to NATS %s at %s",
            nc.connected_server_version,
            nc.connected_url,
        )

        js = nc.jetstream()
        await js.subscribe(
            subject=nats_subject,
            queue=nats_queue,
            manual_ack=True,
            cb=handle_message,
        )


@click.command()
@click.option("nats_servers", "--nats-server", multiple=True, required=True)
@click.option("--nats-subject", default="tasks")
@click.option("--nats-queue", default="worker")
@click.option("--postgres-app-dsn", required=True)
@click.option("--postgres-fingerprint-dsn", required=True)
@click.option("--postgres-ingest-dsn", required=True)
@click.option("--postgres-musicbrainz-dsn", required=True)
def main(
    nats_servers: Iterable[str],
    nats_subject: str,
    nats_queue: str,
    postgres_app_dsn: str,
    postgres_fingerprint_dsn: str,
    postgres_ingest_dsn: str,
    postgres_musicbrainz_dsn: str,
) -> None:
    asyncio.run(
        worker(
            nats_servers=list(nats_servers),
            nats_subject=nats_subject,
            nats_queue=nats_queue,
            postgres_app_dsn=postgres_app_dsn,
            postgres_fingerprint_dsn=postgres_fingerprint_dsn,
            postgres_ingest_dsn=postgres_ingest_dsn,
            postgres_musicbrainz_dsn=postgres_musicbrainz_dsn,
        )
    )


if __name__ == "__main__":
    main(auto_envvar_prefix="ASERVER_")
