# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import logging
from sqlalchemy import sql
from acoustid import tables as schema

logger = logging.getLogger(__name__)


def find_or_insert_foreignid_vendor(conn, name):
    with conn.begin():
        query = sql.select([schema.foreignid_vendor.c.id], schema.foreignid_vendor.c.name == name)
        id = conn.execute(query).scalar()
        if id is None:
            insert_stmt = schema.foreignid_vendor.insert().values(name=name)
            id = conn.execute(insert_stmt).inserted_primary_key[0]
            logger.info("Inserted foreign ID vendor %d with name %s", id, name)
    return id


def find_or_insert_foreignid(conn, full_name):
    vendor, name = full_name.split(':', 1)
    with conn.begin():
        vendor_id = find_or_insert_foreignid_vendor(conn, vendor)
        query = sql.select([schema.foreignid.c.id],
            sql.and_(schema.foreignid.c.vendor_id == vendor_id,
                     schema.foreignid.c.name == name))
        id = conn.execute(query).scalar()
        if id is None:
            insert_stmt = schema.foreignid.insert().values(vendor_id=vendor_id, name=name)
            id = conn.execute(insert_stmt).inserted_primary_key[0]
            logger.info("Inserted foreign ID %d with name %s", id, full_name)
    return id

