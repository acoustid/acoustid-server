# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import logging
from sqlalchemy import sql
from acoustid import tables as schema

logger = logging.getLogger(__name__)


def lookup_application_id_by_apikey(conn, apikey):
    query = sql.select([schema.application.c.id], schema.application.c.apikey == apikey)
    return conn.execute(query).scalar()


def find_applications_by_account(conn, account_id):
    query = schema.application.select(schema.application.c.account_id == account_id)
    query = query.order_by(schema.application.c.name)
    return [dict(i) for i in conn.execute(query).fetchall()]

