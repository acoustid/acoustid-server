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


def insert_application(conn, data):
    """
    Insert a new application into the database
    """
    with conn.begin():
        insert_stmt = schema.application.insert().values({
            'name': data['name'],
            'version': data['version'],
            'email': data.get('email'),
            'website': data.get('website'),
            'account_id': data['account_id'],
            'apikey': sql.text('generate_api_key()'),
        })
        id = conn.execute(insert_stmt).inserted_primary_key[0]
    logger.debug("Inserted application %r with data %r", id, data)
    return id

