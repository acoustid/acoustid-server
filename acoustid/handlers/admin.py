# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details. 

from acoustid.handler import Handler, Response
from acoustid.track import merge_missing_mbids


class MergeMissingMBIDsHandler(Handler):

    def __init__(self, conn):
        self.conn = conn

    @classmethod
    def create_from_server(cls, server):
        return cls(server.engine.connect())

    def handle(self, req):
        merge_missing_mbids(self.conn)
        return Response('OK')

