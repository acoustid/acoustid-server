# Copyright (C) 2015 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import logging
from acoustid import tables

logger = logging.getLogger(__name__)


QUERIES = [
    ('account.all', 'SELECT count(*) FROM account'),
    ('account.musicbrainz', 'SELECT count(*) FROM account WHERE mbuser IS NOT NULL'),
    ('account.openid', 'SELECT count(DISTINCT account_id) FROM account_openid'),
    ('account.active', 'SELECT count(DISTINCT account_id) FROM source'),
    ('application.all', 'SELECT count(*) FROM application'),
    ('format.all', 'SELECT count(*) FROM format'),
    ('fingerprint.all', 'SELECT count(*) FROM fingerprint'),
    ('track_mbid.all', 'SELECT count(*) FROM track_mbid'),
    ('mbid.all', 'SELECT count(DISTINCT mbid) FROM track_mbid'),
    ('track.all', 'SELECT count(*) FROM track'),
    ('submission.all', 'SELECT sum(submission_count) FROM account'),
    ('submission.unhandled', 'SELECT count(*) FROM submission WHERE not handled'),
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


def main(script, opts, args):
    if script.config.cluster.role != 'master':
        logger.info('Not running update_stats in slave mode')
        return

    db = script.engine.connect()
    with db.begin():

        insert = tables.stats.insert()
        for name, query in QUERIES:
            logger.info('Updating stats %s', name)
            value = db.execute(query).scalar()
            db.execute(insert.values({'name': name, 'value': value}))

        for i, value in get_track_count_stats(db, MBID_TRACK_QUERY):
            name = 'mbid.%dtracks' % i
            logger.info('Updating stats %s', name)
            db.execute(insert.values({'name': name, 'value': value}))

        for i, value in get_track_count_stats(db, TRACK_MBID_QUERY):
            name = 'track.%dmbids' % i
            logger.info('Updating stats %s', name)
            db.execute(insert.values({'name': name, 'value': value}))
