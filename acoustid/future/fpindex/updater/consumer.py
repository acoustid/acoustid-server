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
    instance: str, index_url: str, index_name: str, nats_url: str, stream_name: str
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

        sub = await js.pull_subscribe(
            stream=stream_name,
            subject=f"{SUBJECT_NAME}.*",
            durable=f"fpindex-updater.{instance}",
            config=ConsumerConfig(),
        )

        while not shutdown_event.is_set():
            lsn = 0
            batch1 = BatchUpdate()
            batch2 = BatchUpdate()
            messages = await sub.fetch(BATCH_SIZE, timeout=10.0, heartbeat=1.0)
            for msg in messages:
                data = msgspec.msgpack.decode(msg.data, type=FingerprintChange)
                lsn = max(lsn, data.lsn)
                if isinstance(data, (FingerprintInsert, FingerprintUpdate)):
                    hashes = decode_legacy_fingerprint(
                        data.hashes, base64=False, signed=True
                    ).hashes
                    batch1.insert(data.id, list(hashes))
                    batch2.insert(data.id, [data.simhash])
                elif isinstance(data, FingerprintDelete):
                    batch1.delete(data.id)
                    batch2.delete(data.id)
            batch1.set_attribute("lsn", data.lsn)
            batch2.set_attribute("lsn", data.lsn)
            await fpindex.update(index_name, batch1)
            await fpindex.update(index_name + ".sh", batch2)
            for msg in messages:
                await msg.ack()


@click.command()
@click.option("--instance", default="default")
@click.option("--index-url", default="http://localhost:5000")
@click.option("--index-name", default="acoustid")
@click.option("--nats-url", default="nats://localhost:4222")
@click.option("--stream-name", default=STREAM_NAME)
def main(
    instance: str, index_url: str, index_name: str, nats_url: str, stream_name: str
) -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(update_index(instance, index_url, index_name, nats_url, stream_name))


if __name__ == "__main__":
    main()
