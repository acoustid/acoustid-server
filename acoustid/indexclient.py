# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import errno
import socket
import select
import time
import logging
from collections import namedtuple, deque

logger = logging.getLogger(__name__)

CRLF = '\r\n'


def encode_fp(data):
    return ','.join(map(str, data))


Result = namedtuple('Result', ['id', 'score'])


class IndexClientError(Exception):
    """Base class for all errors."""
    pass


class IndexClient(object):

    def __init__(self, host='127.0.0.1', port=6080, timeout=10):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.socket_timeout = 0.25
        self.in_transaction = False
        self.created = time.time()
        self.sock = None
        self._buffer = ''
        self._connect()

    def __repr__(self):
        return '<%s(%s, %s) instance at %s>' % (self.__class__.__name__,
            self.host, self.port, hex(id(self)))

    def __del__(self):
        if self.sock is not None:
            logger.warn('Deleted without being explicitly closed')
            self.close()

    def _connect(self):
        logger.debug("Connecting to index server at %s:%s", self.host, self.port)
        try:
            self.sock = socket.create_connection((self.host, self.port), self.socket_timeout)
            self.sock.setblocking(0)
        except socket.error:
            raise IndexClientError('unable to connect to the index server at %s:%s' % (self.host, self.port))

    def _putline(self, line):
        self.sock.sendall('%s%s' % (line, CRLF))

    def _getline(self, timeout=None):
        pos = self._buffer.find(CRLF)
        if timeout is None:
            timeout = self.timeout
        deadline = time.time() + timeout
        while pos == -1:
            try:
                ready_to_read, ready_to_write, in_error = select.select([self.sock], [], [self.sock], self.socket_timeout)
            except select.error, e:
                if getattr(e, 'errno', None) == errno.EINTR:
                    continue
                raise
            if in_error:
                raise IndexClientError("socket error")
            if ready_to_read:
                while True:
                    try:
                        data = self.sock.recv(1024)
                    except socket.error, e:
                        if e.errno == errno.EINTR:
                            continue
                        if e.errno == errno.EAGAIN:
                            break
                        raise
                    if not data:
                        break
                    self._buffer += data
                pos = self._buffer.find(CRLF)
            if time.time() > deadline:
                raise IndexClientError("read timeout exceeded")
        line = self._buffer[:pos]
        self._buffer = self._buffer[pos+len(CRLF):]
        return line

    def _request(self, request, timeout=None):
        self._putline(request)
        line = self._getline(timeout=timeout)
        if line.startswith('OK '):
            return line[3:]
        raise IndexClientError(line)

    def ping(self):
        line = self._request('echo', timeout=1.0)
        return True

    def get_attribute(self, name):
        return self._request('get attribute %s' % (name,))

    def set_attribute(self, name, value):
        self._request('set attribute %s %s' % (name, value))
        return True

    def search(self, fingerprint):
        line = self._request('search %s' % (encode_fp(fingerprint),))
        if not line:
            return []
        matches = [Result(*map(int, r.split(':'))) for r in line.split(' ')]
        return matches

    def begin(self):
        if self.in_transaction:
            raise IndexClientError('called begin() while in transaction')
        self._request('begin')
        self.in_transaction = True

    def commit(self):
        if not self.in_transaction:
            raise IndexClientError('called commit() without a transaction')
        self._request('commit', timeout=60.0*10)
        self.in_transaction = False

    def rollback(self):
        if not self.in_transaction:
            raise IndexClientError('called rollback() without a transaction')
        self._request('rollback')
        self.in_transaction = False

    def insert(self, id, fingerprint):
        #logger.debug("Inserting %s %s", id, fingerprint)
        return self._request('insert %d %s' % (id, encode_fp(fingerprint)), timeout=60.0*10)

    def close(self):
        try:
            if self.in_transaction:
                self.rollback()
            self._putline('quit')
            self.sock.close()
        except StandardError:
            logger.exception("Error while closing connection %s", self)
        self.sock = None


class IndexClientWrapper(object):

    def __init__(self, pool=None, client=None):
        self._pool = pool
        self._client = client
        self.ping = self._client.ping
        self.search = self._client.search
        self.begin = self._client.begin
        self.commit = self._client.commit
        self.rollback = self._client.rollback
        self.insert = self._client.insert
        self.get_attribute = self._client.get_attribute
        self.set_attribute = self._client.set_attribute

    def close(self):
        if self._client.in_transaction:
            self._client.rollback()
        self._pool._release(self._client)


class IndexClientPool(object):

    def __init__(self, max_idle_clients=5, recycle=-1, **kwargs):
        self.max_idle_clients = max_idle_clients
        self.recycle = recycle
        self.clients = deque()
        self.args = kwargs

    def dispose(self):
        while self.clients:
            client = self.clients.popleft()
            client.close()

    def _release(self, client):
        if len(self.clients) >= self.max_idle_clients:
            logger.debug("Too many idle connections, closing %s", client)
            client.close()
        else:
            #logger.debug("Checking in connection %s", client)
            self.clients.append(client)

    def connect(self):
        client = None
        if self.clients:
            client = self.clients.popleft()
            try:
                if self.recycle > 0 and client.created + self.recycle < time.time():
                    logger.debug("Recycling connection %s after %d seconds", client, self.recycle)
                    raise IndexClientError()
                else:
                    client.ping()
            except IndexClientError:
                client.close()
                client = None
        if client is None:
            client = IndexClient(**self.args)
        #logger.debug("Checking out connection %s", client)
        return IndexClientWrapper(self, client)

