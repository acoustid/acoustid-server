# Copyright (C) 2026 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import socket
import threading
from typing import Iterator

import pytest

from acoustid.indexclient import CRLF, IndexClient, IndexClientError, IndexClientPool


class FakeIndexServer(object):
    """Just enough of the index server to answer a ping."""

    def __init__(self) -> None:
        self.sock = socket.socket()
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(8)
        self.host, self.port = self.sock.getsockname()
        self.thread = threading.Thread(target=self._accept, daemon=True)
        self.thread.start()

    def _accept(self) -> None:
        while True:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            threading.Thread(target=self._handle, args=(conn,), daemon=True).start()

    def _handle(self, conn: socket.socket) -> None:
        buffer = b""
        with conn:
            while True:
                try:
                    data = conn.recv(1024)
                except OSError:
                    return
                if not data:
                    return
                buffer += data
                while CRLF in buffer:
                    _, buffer = buffer.split(CRLF, 1)
                    try:
                        conn.sendall(b"OK " + CRLF)
                    except OSError:
                        return

    def close(self) -> None:
        self.sock.close()


class FailingSocket(object):
    """A connected socket that fails one operation, as a dead peer would.

    ``socket`` objects do not allow their methods to be replaced, so the client
    is handed this proxy instead.
    """

    def __init__(
        self,
        sock: socket.socket,
        error: OSError,
        method: str = "sendall",
    ) -> None:
        self._sock = sock
        self._error = error
        self._method = method

    def sendall(self, data: bytes) -> None:
        if self._method == "sendall":
            raise self._error
        self._sock.sendall(data)

    def recv(self, size: int) -> bytes:
        if self._method == "recv":
            raise self._error
        return self._sock.recv(size)

    def __getattr__(self, name: str):  # type: ignore[no-untyped-def]
        return getattr(self._sock, name)


@pytest.fixture
def index_server() -> Iterator[FakeIndexServer]:
    server = FakeIndexServer()
    yield server
    server.close()


def test_ping(index_server: FakeIndexServer) -> None:
    client = IndexClient(host=index_server.host, port=index_server.port)
    assert client.ping() is True
    client.close()


def test_send_failure_is_wrapped(index_server: FakeIndexServer) -> None:
    """A socket error while sending must not escape as a raw socket error.

    Every caller of this client guards with ``except IndexClientError``, so
    anything else slips past the handler written to catch it.
    """
    client = IndexClient(host=index_server.host, port=index_server.port)
    assert client.sock is not None
    client.sock = FailingSocket(  # type: ignore[assignment]
        client.sock, BrokenPipeError(32, "Broken pipe"), "sendall"
    )

    with pytest.raises(IndexClientError) as excinfo:
        client.ping()
    assert isinstance(excinfo.value.__cause__, BrokenPipeError)
    # The connection is unusable, so it must not be handed out again.
    assert client.sock is None


def test_receive_failure_is_wrapped(index_server: FakeIndexServer) -> None:
    client = IndexClient(host=index_server.host, port=index_server.port)
    assert client.sock is not None
    # The request goes out and the server answers, so select reports the socket
    # readable and the failure lands on the read.
    client.sock = FailingSocket(  # type: ignore[assignment]
        client.sock, ConnectionResetError(104, "Connection reset by peer"), "recv"
    )

    with pytest.raises(IndexClientError) as excinfo:
        client.ping()
    assert isinstance(excinfo.value.__cause__, ConnectionResetError)
    assert client.sock is None


def test_pool_replaces_connection_whose_peer_is_gone(
    index_server: FakeIndexServer,
) -> None:
    """The pool pings a pooled connection so it can discard the dead ones.

    That check guards on IndexClientError, so a send failure that escaped
    unwrapped would propagate out of connect() instead of being replaced.
    """
    pool = IndexClientPool(host=index_server.host, port=index_server.port)

    wrapper = pool.connect()
    pooled = wrapper._client
    wrapper.close()
    assert list(pool.clients) == [pooled]

    assert pooled.sock is not None
    pooled.sock = FailingSocket(  # type: ignore[assignment]
        pooled.sock, BrokenPipeError(32, "Broken pipe"), "sendall"
    )

    replacement = pool.connect()
    assert replacement._client is not pooled
    assert replacement.ping() is True
    replacement.close()

    pool.dispose()
