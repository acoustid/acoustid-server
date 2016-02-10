# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import logging
from sqlalchemy import sql
from acoustid import tables as schema
from acoustid.utils import generate_api_key

logger = logging.getLogger(__name__)


def lookup_account_id_by_apikey(conn, apikey):
    query = sql.select([schema.account.c.id], schema.account.c.apikey == apikey)
    return conn.execute(query).scalar()


def lookup_account_id_by_mbuser(conn, mbuser):
    query = sql.select([schema.account.c.id], sql.func.lower(schema.account.c.mbuser) == sql.func.lower(mbuser))
    return conn.execute(query).scalar()


def lookup_account_id_by_openid(conn, openid):
    query = sql.select([schema.account_openid.c.account_id], schema.account_openid.c.openid == openid)
    return conn.execute(query).scalar()


def get_account_details(conn, id):
    query = schema.account.select(schema.account.c.id == id)
    return conn.execute(query).fetchone()


def get_account_details_by_mbuser(conn, mbuser):
    query = schema.account.select(sql.func.lower(schema.account.c.mbuser) == sql.func.lower(mbuser))
    return conn.execute(query).fetchone()


def update_account_lastlogin(conn, id):
    with conn.begin():
        update_stmt = schema.account.update().where(schema.account.c.id == id)
        update_stmt = update_stmt.values(lastlogin=sql.text('now()'))
        logger.info('%s', update_stmt)
        conn.execute(update_stmt)


def insert_account(conn, data):
    """
    Insert a new account into the database
    """
    with conn.begin():
        insert_stmt = schema.account.insert().values({
            'name': data['name'],
            'mbuser': data.get('mbuser'),
            'created_from': data.get('created_from'),
            'application_id': data.get('application_id'),
            'application_version': data.get('application_version'),
            'lastlogin': sql.text('now()'),
            'apikey': generate_api_key(),
        }).returning(schema.account.c.id, schema.account.c.apikey)
        id, api_key = conn.execute(insert_stmt).fetchone()
        if 'openid' in data:
            insert_stmt = schema.account_openid.insert().values({
                'account_id': id,
                'openid': data['openid'],
            })
            conn.execute(insert_stmt)
    logger.debug("Inserted account %r with data %r", id, data)
    return id, api_key


def reset_account_apikey(conn, id):
    with conn.begin():
        update_stmt = schema.account.update().where(
            schema.account.c.id == id)
        update_stmt = update_stmt.values(apikey=generate_api_key())
        conn.execute(update_stmt)
    logger.debug("Reset API key for account %r", id)


def is_moderator(conn, id):
    query = sql.select([schema.account.c.mbuser], schema.account.c.id == id)
    return bool(conn.execute(query).scalar())

