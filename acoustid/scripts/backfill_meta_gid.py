#!/usr/bin/env python

# Copyright (C) 2019 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import logging

from sqlalchemy import sql
from sqlalchemy.dialects import postgresql as pg

from acoustid import tables
from acoustid.db import FingerprintDB, IngestDB
from acoustid.data.meta import generate_meta_gid

logger = logging.getLogger(__name__)


def get_last_meta_id(fingerprint_db):
    # type: (FingerprintDB) -> int
    query = sql.select([tables.meta_gid_backfill_status.c.last_meta_id])
    return fingerprint_db.execute(query).scalar() or 0


def update_last_meta_id(fingerprint_db, last_meta_id):
    # type: (FingerprintDB, int) -> None
    values = {'id': 1, 'last_meta_id': last_meta_id}
    upsert_stmt = (
        pg.insert(tables.meta_gid_backfill_status).values(values)
        .on_conflict_do_update(index_elements=[tables.meta_gid_backfill_status.c.id], set_=values)
    )
    fingerprint_db.execute(upsert_stmt)


def backfill_meta_gid(fingerprint_db, ingest_db, last_meta_id, limit):
    # type: (FingerprintDB, IngestDB, int, int) -> int
    query = sql.select([tables.meta]).where(tables.meta.c.id >= last_meta_id).order_by(tables.meta.c.id).limit(limit)
    for meta in fingerprint_db.execute(query).fetchall():
        meta_id = meta['id']  # type: int
        if meta_id > last_meta_id:
            last_meta_id = meta_id
        if meta['gid']:
            continue
        meta_gid = generate_meta_gid(dict(meta))
        query = sql.select([tables.meta.c.id], tables.meta.c.gid == meta_gid)
        new_meta_id = fingerprint_db.execute(query).scalar()
        if new_meta_id:
            update_stmt = (
                tables.submission_result.update()
                .where(tables.submission_result.c.meta_id == meta_id)
                .values({'meta_id': new_meta_id, 'meta_gid': meta_gid})
            )
            ingest_db.execute(update_stmt)

            query = (
                sql.select([tables.track_meta.c.track_id])
                .where(tables.track_meta.c.meta_id.in_([meta_id, new_meta_id]))
                .group_by(tables.track_meta.c.track_id)
                .having(sql.func.count(tables.track_meta.c.track_id) > 1)
            )
            track_ids_with_duplicates = [i[0] for i in fingerprint_db.execute(query).fetchall()]
            for track_id in track_ids_with_duplicates:
                query = (
                    tables.track_meta.select()
                    .where(tables.track_meta.c.track_id == track_id)
                    .where(tables.track_meta.c.meta_id == meta_id)
                )
                track_meta = fingerprint_db.execute(query).fetchone()
                update_stmt = (
                    tables.track_meta.update()
                    .where(tables.track_meta.c.track_id == track_id)
                    .where(tables.track_meta.c.meta_id == new_meta_id)
                    .values({'submission_count': tables.track_meta.c.submission_count + track_meta['submission_count'], 'updated': sql.func.now()})
                    .returning(tables.track_meta.c.id)
                )
                new_track_meta_id = fingerprint_db.execute(update_stmt).scalar()
                logger.debug('Merged track_meta %s into %s', track_meta['id'], new_track_meta_id)
                update_stmt = (
                    tables.track_meta_source.update()
                    .where(tables.track_meta_source.c.track_meta_id == track_meta['id'])
                    .values({'track_meta_id': new_track_meta_id})
                )
                ingest_db.execute(update_stmt)
                logger.debug('Merged track_meta_source %s into %s', track_meta['id'], new_track_meta_id)
                delete_stmt = (
                    tables.track_meta.delete()
                    .where(tables.track_meta.c.id == track_meta['id'])
                )
                fingerprint_db.execute(delete_stmt)
                logger.debug('Deleted track_meta %s', track_meta['id'])

            update_stmt = (
                tables.track_meta.update()
                .where(tables.track_meta.c.meta_id == meta_id)
                .values({'meta_id': new_meta_id})
            )
            fingerprint_db.execute(update_stmt)

            insert_stmt = (
                tables.meta_id_history.insert()
                .values({'id': meta_id, 'gid': meta_gid})
            )
            fingerprint_db.execute(insert_stmt)

            delete_stmt = (
                tables.meta.delete()
                .where(tables.meta.c.id == meta_id)
            )
            fingerprint_db.execute(delete_stmt)

        else:
            update_stmt = (
                tables.meta.update()
                .where(tables.meta.c.id == meta_id)
                .values({'gid': meta_gid})
            )
            fingerprint_db.execute(update_stmt)
            update_stmt = (
                tables.submission_result.update()
                .where(tables.submission_result.c.meta_id == meta_id)
                .values({'meta_gid': meta_gid})
            )
            ingest_db.execute(update_stmt)
    return last_meta_id


def run_backfill_meta_gid(script, opts, args):
    if script.config.cluster.role != 'master':
        logger.info('Not running backfill_meta_gid in slave mode')
        return

    while True:
        with script.context(use_two_phase_commit=True) as ctx:
            fingerprint_db = ctx.db.get_fingerprint_db()
            ingest_db = ctx.db.get_ingest_db()
            last_meta_id = get_last_meta_id(fingerprint_db)
            logging.info('Procesing meta from ID %s', last_meta_id)
            new_last_meta_id = backfill_meta_gid(fingerprint_db, ingest_db, last_meta_id, 1000)
            if last_meta_id == new_last_meta_id:
                break
            last_meta_id = new_last_meta_id
            update_last_meta_id(fingerprint_db, last_meta_id)
            ctx.db.session.commit()
