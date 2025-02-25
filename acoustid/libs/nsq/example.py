import gevent

from .client import Consumer, Message


def message_handler(message: Message):
    try:
        print(f"Received message: {message.body.decode()}")
        message.fin()
    except Exception:
        message.req()


consumer = Consumer(
    topic="test_topic",
    channel="test_channel",
    message_handler=message_handler,
    lookupds=["http://localhost:4161"],
    max_in_flight=100,
)

consumer.start()

try:
    while True:
        gevent.sleep(1)
except KeyboardInterrupt:
    consumer.stop()
