# Copyright (C) 2012 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import logging
from acoustid.data.stats import update_lookup_stats, update_user_agent_stats
from acoustid.api import errors
from acoustid.api.v2 import APIHandler, APIHandlerParams
from acoustid.handler import Handler, Response

logger = logging.getLogger(__name__)


class UpdateLookupStatsHandlerParams(APIHandlerParams):

    def parse(self, values, conn):
        super(UpdateLookupStatsHandlerParams, self).parse(values, conn)
        self.secret = values.get('secret')
        self.application_id = values.get('application_id', type=int)
        self.date = values.get('date')
        self.hour = values.get('hour', type=int)
        self.type = values.get('type')
        self.count = values.get('count', type=int)


class UpdateLookupStatsHandler(APIHandler):

    params_class = UpdateLookupStatsHandlerParams

    def _handle_internal(self, params):
        if self.cluster.role != 'master':
            logger.warning('Trying to call update_lookup_stats on %s server', self.cluster.role)
            raise errors.NotAllowedError()
        if self.cluster.secret != params.secret:
            logger.warning('Invalid cluster secret')
            raise errors.NotAllowedError()
        with self.conn.begin():
            update_lookup_stats(self.conn, params.application_id, params.date,
                                params.hour, params.type, params.count)
        return {}


class UpdateUserAgentStatsHandlerParams(APIHandlerParams):

    def parse(self, values, conn):
        super(UpdateUserAgentStatsHandlerParams, self).parse(values, conn)
        self.secret = values.get('secret')
        self.application_id = values.get('application_id', type=int)
        self.date = values.get('date')
        self.user_agent = values.get('user_agent')
        self.ip = values.get('ip')
        self.count = values.get('count', type=int)


class UpdateUserAgentStatsHandler(APIHandler):

    params_class = UpdateUserAgentStatsHandlerParams

    def _handle_internal(self, params):
        if self.cluster.role != 'master':
            logger.warning('Trying to call update_user_agent_stats on %s server', self.cluster.role)
            raise errors.NotAllowedError()
        if self.cluster.secret != params.secret:
            logger.warning('Invalid cluster secret')
            raise errors.NotAllowedError()
        with self.conn.begin():
            update_user_agent_stats(self.conn, params.application_id, params.date,
                                    params.user_agent, params.ip, params.count)
        return {}

