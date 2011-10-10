#!/usr/bin/env python

# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import re
from acoustid.indexclient import IndexClient
from acoustid.script import run_script


def main(script, opts, args):
    conn = script.engine.connect()
    with conn.begin():
        rows = conn.execute("""
            SELECT id, acoustid_extract_query(fingerprint) AS fingerprint
            FROM fingerprint
            WHERE id > (SELECT fingerprint_id FROM fingerprint_index_queue)
            ORDER BY id
            LIMIT 5000
        """)
        max_id = 0
        for row in rows:
            if not max_id:
                idx = IndexClient(host=script.config.index.host,
                                  port=script.config.index.port)
                idx.begin()
            max_id = row['id']
            idx.insert(row['id'], row['fingerprint'])
        if max_id:
            idx.commit()
            idx.close()
            conn.execute("UPDATE fingerprint_index_queue SET fingerprint_id = %s", (max_id,))

run_script(main)

