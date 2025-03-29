import asyncio
import logging
import signal
from contextlib import AsyncExitStack

import click
import msgspec
import nats
from acoustid_ext.fingerprint import decode_legacy_fingerprint
from nats.js.api import ConsumerConfig

from acoustid.future.fpindex.client import BatchUpdate, FingerprintIndexClient
from acoustid.future.fpindex.updater.queue import (
    STREAM_NAME,
    SUBJECT_NAME,
    FingerprintChange,
    FingerprintDelete,
    FingerprintInsert,
    FingerprintUpdate,
)

logger = logging.getLogger(__name__)

BATCH_SIZE = 1000


def shutdown(event: asyncio.Event) -> None:
    logger.info("Shutting down...")
    event.set()


async def update_index(
    instance: str,
    index_url: str,
    index_name: str,
    nats_url: str,
    stream_name: str,
    simhash: bool,
) -> None:
    async with AsyncExitStack() as exit_stack:
        shutdown_event = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, shutdown, shutdown_event)

        fpindex = FingerprintIndexClient(index_url)
        exit_stack.push_async_callback(fpindex.close)

        nc = await nats.connect(nats_url)
        exit_stack.push_async_callback(nc.close)

        js = nc.jetstream()

        subscriber_name = f"fpindex-updater.{instance}"
        if simhash:
            subscriber_name += ".sh"

        sub = await js.pull_subscribe(
            stream=stream_name,
            subject=f"{SUBJECT_NAME}.*",
            durable=subscriber_name,
            config=ConsumerConfig(),
        )

        while not shutdown_event.is_set():
            last_steam_seq = 0
            batch = BatchUpdate()
            messages = await sub.fetch(BATCH_SIZE, timeout=10.0, heartbeat=1.0)
            for msg in messages:
                data = msgspec.msgpack.decode(msg.data, type=FingerprintChange)
                last_steam_seq = max(last_steam_seq, msg.metadata.sequence.stream)
                if isinstance(data, (FingerprintInsert, FingerprintUpdate)):
                    if simhash:
                        batch.insert(data.id, [data.simhash])
                    else:
                        hashes = decode_legacy_fingerprint(
                            data.query, base64=False, signed=True
                        ).hashes
                        batch.insert(data.id, list(hashes))
                elif isinstance(data, FingerprintDelete):
                    batch.delete(data.id)
            batch.set_attribute("nats_stream_seq", last_steam_seq)
            await fpindex.update(index_name, batch)
            for msg in messages:
                await msg.ack()


@click.command()
@click.option("--instance", default="default")
@click.option("--index-url", default="http://localhost:5000")
@click.option("--index-name", default="acoustid")
@click.option("--nats-url", default="nats://localhost:4222")
@click.option("--stream-name", default=STREAM_NAME)
@click.option("--simhash", is_flag=True, default=False)
def main(
    instance: str,
    index_url: str,
    index_name: str,
    nats_url: str,
    stream_name: str,
    simhash: bool,
) -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(
        update_index(instance, index_url, index_name, nats_url, stream_name, simhash)
    )


if __name__ == "__main__":
    main()
