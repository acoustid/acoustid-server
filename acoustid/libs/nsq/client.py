import json
import logging
import random
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

import gevent
import gevent.queue as queue
import gevent.socket as socket
import requests
from requests.exceptions import RequestException

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("nsq_client")

MAGIC_V2 = b"  V2"

FRAME_TYPE_RESPONSE = 0
FRAME_TYPE_ERROR = 1
FRAME_TYPE_MESSAGE = 2

HEARTBEAT_INTERVAL = 30  # seconds
DEFAULT_MAX_RDY_COUNT = 2500


@dataclass
class NsqdServer:
    broadcast_address: str
    tcp_port: int


class Message:
    def __init__(self, conn, msg_id: bytes, body: bytes, attempts: int, timestamp: int):
        self.conn = conn
        self.id = msg_id
        self.body = body
        self.attempts = attempts
        self.timestamp = timestamp

    def fin(self):
        self.conn.fin(self.id)

    def req(self, timeout: int = 0):
        self.conn.req(self.id, timeout)

    def touch(self):
        self.conn.touch(self.id)


class Connection:
    def __init__(
        self,
        host: str,
        port: int,
        topic: str,
        channel: str,
        message_handler: Callable[[Message], None],
        max_rdy: int,
    ):
        self.host = host
        self.port = port
        self.topic = topic
        self.channel = channel
        self.message_handler = message_handler
        self.max_rdy = max_rdy
        self.sock: Optional[socket.socket] = None
        self.rdy = 0
        self.in_flight = 0
        self.last_rdy = 0
        self.running = False
        self.backoff = False
        self.backoff_time = 0
        self.write_queue = queue.Queue()

    def connect(self):
        self.sock = socket.create_connection((self.host, self.port))
        self.sock.send(MAGIC_V2)
        self._identify()
        self._subscribe()
        self.running = True
        gevent.spawn(self.read_loop)
        gevent.spawn(self.write_loop)
        self.update_rdy(1)

    def _identify(self):
        identify = {
            "feature_negotiation": True,
            "heartbeat_interval": HEARTBEAT_INTERVAL * 1000,
            "client_id": "python-client",
            "hostname": "localhost",
        }
        self.send_command("IDENTIFY", json.dumps(identify).encode())
        resp = self._read_response()
        self.features = json.loads(resp)

    def _subscribe(self):
        self.send_command(f"SUB {self.topic} {self.channel}")
        self._read_response()

    def send_command(self, command: str, data: bytes = b""):
        self.write_queue.put((command, data))

    def update_rdy(self, count: int):
        count = min(count, self.max_rdy)
        if count != self.rdy:
            self.send_command(f"RDY {count}")
            self.rdy = count
            self.last_rdy = count

    def _read_response(self) -> bytes:
        assert self.sock is not None
        size_bytes = self.sock.recv(4)
        size = int.from_bytes(size_bytes, byteorder="big")
        data = self.sock.recv(size)
        return data

    def fin(self, msg_id: bytes):
        self.send_command(f"FIN {msg_id.decode()}")

    def req(self, msg_id: bytes, timeout: int = 0):
        self.send_command(f"REQ {msg_id.decode()} {timeout}")

    def touch(self, msg_id: bytes):
        self.send_command(f"TOUCH {msg_id.decode()}")

    def read_loop(self):
        while self.running:
            try:
                size_bytes = self.sock.recv(4)
                if len(size_bytes) < 4:
                    break
                size = int.from_bytes(size_bytes, byteorder="big")
                frame_data = self.sock.recv(size)
                frame_type = int.from_bytes(frame_data[:4], byteorder="big")
                payload = frame_data[4:]

                if frame_type == FRAME_TYPE_MESSAGE:
                    self.handle_message(payload)
                elif frame_type == FRAME_TYPE_RESPONSE:
                    if payload == b"_heartbeat_":
                        self.send_command("NOP")
                elif frame_type == FRAME_TYPE_ERROR:
                    logger.error("Received error: %s", payload.decode())
            except Exception as e:
                logger.error("Read loop error: %s", e)
                break

        logger.info("Connection to %s:%d closed", self.host, self.port)
        self.running = False

    def handle_message(self, data: bytes):
        timestamp = int.from_bytes(data[:8], byteorder="big")
        attempts = int.from_bytes(data[8:10], byteorder="big")
        msg_id = data[10:26]
        body = data[26:]
        message = Message(self, msg_id, body, attempts, timestamp)
        self.in_flight += 1
        gevent.spawn(self.process_message, message)

    def process_message(self, message: Message):
        try:
            self.message_handler(message)
            message.fin()
        except Exception as e:
            logger.error("Message processing failed: %s", e)
            message.req()
        finally:
            self.in_flight -= 1

    def write_loop(self):
        while self.running:
            try:
                command, data = self.write_queue.get()
                frame = command.encode() + b"\n"
                if data:
                    frame += len(data).to_bytes(4, byteorder="big") + data
                self.sock.sendall(frame)
            except Exception as e:
                logger.error("Write loop error: %s", e)
                break

    def close(self):
        self.running = False
        if self.sock:
            self.sock.close()


class NsqlookupdDiscovery:
    def __init__(self, lookupds: List[str], topic: str, interval: int):
        self.lookupds = lookupds
        self.topic = topic
        self.interval = interval
        self.current_nsqds: List[NsqdServer] = []

    def poll(self) -> List[NsqdServer]:
        nsqd_set = set()
        for lookupd in self.lookupds:
            try:
                resp = requests.get(f"{lookupd}/lookup", params={"topic": self.topic})
                data = resp.json()
                for producer in data["producers"]:
                    nsqd = NsqdServer(
                        producer["broadcast_address"], producer["tcp_port"]
                    )
                    nsqd_set.add((nsqd.broadcast_address, nsqd.tcp_port))
            except RequestException as e:
                logger.error("Lookupd query failed: %s", e)
        return [NsqdServer(addr[0], addr[1]) for addr in nsqd_set]

    def run(self, callback: Callable[[List[NsqdServer]], None]):
        while True:
            try:
                jitter = random.uniform(0.8, 1.2)
                gevent.sleep(self.interval * jitter)
                new_nsqds = self.poll()
                if new_nsqds != self.current_nsqds:
                    callback(new_nsqds)
                    self.current_nsqds = new_nsqds
            except Exception as e:
                logger.error("Discovery error: %s", e)


class Consumer:
    def __init__(
        self,
        topic: str,
        channel: str,
        message_handler: Callable[[Message], None],
        lookupds: List[str] = None,
        nsqds: List[Tuple[str, int]] = None,
        max_in_flight: int = 1,
        lookupd_poll_interval: int = 60,
    ):
        self.topic = topic
        self.channel = channel
        self.message_handler = message_handler
        self.max_in_flight = max_in_flight
        self.connections: Dict[str, Connection] = {}
        self.lookupd_discovery: Optional[NsqlookupdDiscovery] = None
        self.running = False

        if lookupds:
            self.lookupd_discovery = NsqlookupdDiscovery(
                lookupds, topic, lookupd_poll_interval
            )
        elif nsqds:
            for host, port in nsqds:
                self.add_connection(host, port)

    def start(self):
        self.running = True
        if self.lookupd_discovery:
            gevent.spawn(self.lookupd_discovery.run, self.update_connections)
        gevent.spawn(self.rdy_loop)

    def stop(self):
        self.running = False
        for conn in self.connections.values():
            conn.close()

    def add_connection(self, host: str, port: int):
        key = f"{host}:{port}"
        if key not in self.connections:
            conn = Connection(
                host,
                port,
                self.topic,
                self.channel,
                self.message_handler,
                DEFAULT_MAX_RDY_COUNT,
            )
            self.connections[key] = conn
            conn.connect()

    def remove_connection(self, host: str, port: int):
        key = f"{host}:{port}"
        if key in self.connections:
            self.connections[key].close()
            del self.connections[key]

    def update_connections(self, nsqds: List[NsqdServer]):
        current = set(f"{n.broadcast_address}:{n.tcp_port}" for n in nsqds)
        existing = set(self.connections.keys())

        # Add new connections
        for nsqd in nsqds:
            key = f"{nsqd.broadcast_address}:{nsqd.tcp_port}"
            if key not in existing:
                self.add_connection(nsqd.broadcast_address, nsqd.tcp_port)

        # Remove old connections
        for key in existing - current:
            host, port = key.split(":")
            self.remove_connection(host, int(port))

    def rdy_loop(self):
        while self.running:
            try:
                if not self.connections:
                    gevent.sleep(1)
                    continue

                total_rdy = sum(c.rdy for c in self.connections.values())
                available = self.max_in_flight - total_rdy
                if available <= 0:
                    gevent.sleep(0.1)
                    continue

                per_conn = max(available // len(self.connections), 1)
                for conn in self.connections.values():
                    new_rdy = min(conn.rdy + per_conn, conn.max_rdy)
                    if new_rdy != conn.rdy:
                        conn.update_rdy(new_rdy)
                        available -= new_rdy - conn.rdy
                        if available <= 0:
                            break

                gevent.sleep(0.1)
            except Exception as e:
                logger.error("RDY loop error: %s", e)
                gevent.sleep(1)

    def is_starved(self) -> bool:
        for conn in self.connections.values():
            if conn.in_flight >= (conn.last_rdy * 0.85):
                return True
        return False
