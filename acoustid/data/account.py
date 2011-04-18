# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import logging
from sqlalchemy import sql
from acoustid import tables as schema

logger = logging.getLogger(__name__)


def lookup_account_id_by_apikey(conn, apikey):
    query = sql.select([schema.account.c.id], schema.account.c.apikey == apikey)
    return conn.execute(query).scalar()

