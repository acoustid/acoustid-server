# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import socket
import select
import time
from collections import namedtuple

CRLF = '\r\n'


def encode_fp(data):
    return ','.join(map(str, data))


Result = namedtuple('Result', ['id', 'score'])


class IndexClientError(Exception):
    pass


class IndexClient(object):

    def __init__(self, host, port=6000, timeout=10):
        self.host = host
        self.port = port
        self.timeout = timeout
        self._buffer = ''
        self._connect()

    def _connect(self):
        self.sock = socket.create_connection((self.host, self.port))
        self.sock.setblocking(0)

    def _putline(self, line):
        self.sock.sendall('%s%s' % (line, CRLF))

    def _getline(self, timeout=None):
        pos = self._buffer.find(CRLF)
        if timeout is None:
            timeout = self.timeout
        deadline = time.time() + timeout
        while pos == -1:
            ready_to_read, ready_to_write, in_error = select.select([self.sock], [], [self.sock], 0.5)
            if in_error:
                raise IndexClientError("socket error")
            if ready_to_read:
                self._buffer += self.sock.recv(1024)
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

    def search(self, fingerprint):
        line = self._request('search %s' % (encode_fp(fingerprint),))
        matches = [Result(*map(int, r.split(':'))) for r in line.split(' ')]
        return matches

    def begin(self):
        return self._request('begin')

    def commit(self):
        return self._request('commit')

    def insert(self, id, fingerprint):
        return self._request('insert %d %s' % (id, encode_fp(fingerprint)))

