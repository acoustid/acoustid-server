# Copyright (C) 2015 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import logging
from acoustid import tables

logger = logging.getLogger(__name__)


QUERIES = [
    ('app', 'account.all', 'SELECT count(*) FROM account'),
    ('app', 'account.musicbrainz', 'SELECT count(*) FROM account WHERE mbuser IS NOT NULL'),
    ('app', 'account.openid', 'SELECT count(DISTINCT account_id) FROM account_openid'),
    ('app', 'account.active', 'SELECT count(DISTINCT account_id) FROM source'),
    ('app', 'application.all', 'SELECT count(*) FROM application'),
    ('app', 'format.all', 'SELECT count(*) FROM format'),
    ('fingerprint', 'fingerprint.all', 'SELECT count(*) FROM fingerprint'),
    ('fingerprint', 'track_mbid.all', 'SELECT count(*) FROM track_mbid'),
    ('fingerprint', 'mbid.all', 'SELECT count(DISTINCT mbid) FROM track_mbid'),
    ('fingerprint', 'track.all', 'SELECT count(*) FROM track'),
    ('app', 'submission.all', 'SELECT sum(submission_count) FROM account'),
    ('ingest', 'submission.unhandled', 'SELECT count(*) FROM submission WHERE not handled'),
]


MBID_TRACK_QUERY = '''
    SELECT track_count, count(*) mbid_count
    FROM (
        SELECT count(track_id) track_count
        FROM track_mbid
        WHERE disabled=false
        GROUP BY mbid
    ) a
    GROUP BY track_count ORDER BY track_count
'''


TRACK_MBID_QUERY = '''
    SELECT mbid_count, count(*) track_count
    FROM (
        SELECT count(tm.mbid) mbid_count
        FROM track t
        LEFT JOIN track_mbid tm ON t.id=tm.track_id AND tm.disabled=false
        GROUP BY t.id
    ) a
    GROUP BY mbid_count ORDER BY mbid_count
'''


def get_track_count_stats(db, query):
    counts = dict((i, 0) for i in range(11))
    for count_1, count_2 in db.execute(query):
        if count_1 >= 10:
            count_1 = 10
        counts[count_1] += count_2
    return sorted(counts.items())


def run_update_stats(script):
    if script.config.cluster.role != 'master':
        logger.info('Not running update_stats in slave mode')
        return

    with script.context() as ctx:
        insert = tables.stats.insert()
        for bind_key, name, query in QUERIES:
            logger.info('Updating stats %s', name)
            value = ctx.db.connection(bind_key).execute(query).scalar()
            ctx.db.get_app_db().execute(insert.values({'name': name, 'value': value}))

        for i, value in get_track_count_stats(ctx.db.get_fingerprint_db(), MBID_TRACK_QUERY):
            name = 'mbid.%dtracks' % i
            logger.info('Updating stats %s', name)
            ctx.db.get_app_db().execute(insert.values({'name': name, 'value': value}))

        for i, value in get_track_count_stats(ctx.db.get_fingerprint_db(), TRACK_MBID_QUERY):
            name = 'track.%dmbids' % i
            logger.info('Updating stats %s', name)
            ctx.db.get_app_db().execute(insert.values({'name': name, 'value': value}))

        ctx.db.session.commit()
