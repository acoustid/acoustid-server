# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import errno
import logging
import select
import socket
import time
from collections import deque, namedtuple
from typing import Any, List

logger = logging.getLogger(__name__)

CRLF = b"\r\n"


def encode_fp(data):
    return ",".join(map(str, data))


Result = namedtuple("Result", ["id", "score"])


class IndexClientError(Exception):
    """Base class for all errors."""

    pass


class Index(object):
    def begin(self):
        # type: () -> None
        raise NotImplementedError(self.begin)

    def search(self, fingerprint):
        # type: (List[int]) -> List[Result]
        raise NotImplementedError(self.search)

    def commit(self):
        # type: () -> None
        raise NotImplementedError(self.commit)

    def insert(self, fingerprint_id, fingerprint_hashes):
        # type: (int, List[int]) -> None
        raise NotImplementedError(self.commit)

    def get_attribute(self, name):
        # type: (str) -> str
        raise NotImplementedError(self.get_attribute)


class IndexClient(Index):
    def __init__(self, host="127.0.0.1", port=6080, timeout=10):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.socket_timeout = 0.25
        self.connect_timeout = self.socket_timeout * 4
        self.in_transaction = False
        self.created = time.time()
        self.sock = None
        self._buffer = b""
        self._connect()

    def __str__(self):
        if self.sock is not None:
            return "{}->{}:{}".format(self.sock.getsockname(), self.host, self.port)
        else:
            return "{}:{}".format(self.host, self.port)

    def __repr__(self):
        return "<%s(%s, %s) instance at %s>" % (
            self.__class__.__name__,
            self.host,
            self.port,
            hex(id(self)),
        )

    def __del__(self):
        if self.sock is not None:
            logger.warn("Deleted without being explicitly closed")
            self.close()

    def _connect(self):
        logger.debug("Connecting to index server at %s:%s", self.host, self.port)
        try:
            self.sock = socket.create_connection(
                (self.host, self.port), self.connect_timeout
            )
            self.sock.setblocking(False)
        except socket.error as e:
            raise IndexClientError(
                "unable to connect to the index server at %s:%s (%s)"
                % (self.host, self.port, e)
            )

    def _putline(self, line: str) -> None:
        assert self.sock is not None
        request = b"%s%s" % (line.encode("utf8"), CRLF)
        logger.debug("Sending request %r", request)
        self.sock.sendall(request)

    def _getline(self, timeout=None):
        assert self.sock is not None
        pos = self._buffer.find(CRLF)
        if timeout is None:
            timeout = self.timeout
        deadline = time.time() + timeout
        while pos == -1:
            try:
                ready_to_read, ready_to_write, in_error = select.select(
                    [self.sock], [], [self.sock], self.socket_timeout
                )
            except select.error as e:
                if getattr(e, "errno", None) == errno.EINTR:
                    continue
                self.close()
                raise
            if in_error:
                logger.debug("Failed to receive response due to select error")
                self.close()
                raise IndexClientError("socket error")
            if ready_to_read:
                while True:
                    try:
                        data = self.sock.recv(1024)
                    except socket.error as e:
                        if e.errno == errno.EINTR:
                            continue
                        if e.errno == errno.EAGAIN:
                            break
                        logger.debug("Failed to receive response due to socket error")
                        self.close()
                        raise
                    if not data:
                        break
                    self._buffer += data
                pos = self._buffer.find(CRLF)
            if time.time() > deadline:
                logger.debug("Failed to receive response due to timeout")
                self.close()
                raise IndexClientError("read timeout exceeded")
        line = self._buffer[:pos]
        logger.debug("Received response %r", line)
        pos += len(CRLF)
        self._buffer = self._buffer[pos:]
        return line.decode("utf8")

    def _request(self, request, timeout=None):
        self._putline(request)
        line = self._getline(timeout=timeout)
        if line.startswith("OK "):
            return line[3:]
        if "unknown command" in line:
            self.close()
        raise IndexClientError(line)

    def ping(self):
        self._request("echo", timeout=1.0)
        return True

    def get_attribute(self, name):
        return self._request("get attribute %s" % (name,))

    def set_attribute(self, name, value):
        self._request("set attribute %s %s" % (name, value))
        return True

    def search(self, fingerprint):
        line = self._request("search %s" % (encode_fp(fingerprint),))
        if not line:
            return []
        matches = [Result(*map(int, r.split(":"))) for r in line.split(" ")]
        return matches

    def begin(self):
        if self.in_transaction:
            raise IndexClientError("called begin() while in transaction")
        self._request("begin")
        self.in_transaction = True

    def commit(self):
        if not self.in_transaction:
            raise IndexClientError("called commit() without a transaction")
        self._request("commit", timeout=60.0 * 10)
        self.in_transaction = False

    def rollback(self):
        if not self.in_transaction:
            raise IndexClientError("called rollback() without a transaction")
        self._request("rollback")
        self.in_transaction = False

    def insert(self, id, fingerprint):
        # logger.debug("Inserting %s %s", id, fingerprint)
        return self._request(
            "insert %d %s" % (id, encode_fp(fingerprint)), timeout=60.0 * 10
        )

    def close(self):
        try:
            if self.sock is not None:
                if self.in_transaction:
                    try:
                        self.rollback()
                    except Exception:
                        logger.exception("Error while trying to rollback transaction")
                self.sock.close()
        except Exception:
            logger.exception("Error while closing connection %s", self)
        self.sock = None


class IndexClientWrapper(Index):
    def __init__(self, pool=None, client=None):
        self._pool = pool
        self._client = client
        self.ping = self._client.ping  # type: ignore
        self.search = self._client.search  # type: ignore
        self.begin = self._client.begin  # type: ignore
        self.commit = self._client.commit  # type: ignore
        self.rollback = self._client.rollback  # type: ignore
        self.insert = self._client.insert  # type: ignore
        self.get_attribute = self._client.get_attribute  # type: ignore
        self.set_attribute = self._client.set_attribute  # type: ignore

    def __enter__(self):
        # type: () -> IndexClientWrapper
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # type: (Any, Any, Any) -> None
        self.close()

    def __str__(self):
        return str(self._client)

    def close(self):
        if self._client.in_transaction:
            self._client.rollback()
        self._pool._release(self._client)


class IndexClientPool(object):
    def __init__(self, max_idle_clients=5, recycle=-1, **kwargs) -> None:
        self.max_idle_clients = max_idle_clients
        self.recycle = recycle
        self.clients: deque[IndexClient] = deque()
        self.args = kwargs

    def dispose(self) -> None:
        logger.debug("Closing all connections")
        while self.clients:
            client = self.clients.popleft()
            logger.debug("Closing connection %s", client)
            client.close()

    def _release(self, client: IndexClient) -> None:
        if client.sock is None:
            logger.debug("Discarding closed connection %s", client)
        else:
            if len(self.clients) >= self.max_idle_clients:
                logger.debug("Too many idle connections, closing %s", client)
                client.close()
            else:
                logger.debug("Checking in connection %s", client)
                self.clients.append(client)

    def connect(self) -> IndexClientWrapper:
        client: IndexClient | None = None
        if self.clients:
            client = self.clients.popleft()
            assert client is not None
            try:
                if self.recycle > 0 and client.created + self.recycle < time.time():
                    logger.debug(
                        "Recycling connection %s after %d seconds", client, self.recycle
                    )
                    raise IndexClientError()
                else:
                    client.ping()
            except IndexClientError:
                client.close()
                client = None
        if client is None:
            client = IndexClient(**self.args)
        logger.debug("Checking out connection %s", client)
        return IndexClientWrapper(self, client)
