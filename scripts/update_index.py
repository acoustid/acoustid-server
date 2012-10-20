#!/usr/bin/env python

# Copyright (C) 2011-2012 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import re
from acoustid.indexclient import IndexClient
from acoustid.script import run_script


def main(script, opts, args):
    conn = script.engine.connect()
    with conn.begin():
        idx = script.index.connect()
        max_id = int(idx.get_attribute('max_document_id') or '0')
        rows = conn.execute("""
            SELECT id, acoustid_extract_query(fingerprint) AS fingerprint
            FROM fingerprint WHERE id > %s ORDER BY id LIMIT 10000
        """, (max_id,))
        has_rows = False
        for row in rows:
            if not has_rows:
                idx.begin()
                has_rows = True
            idx.insert(row['id'], row['fingerprint'])
        if has_rows:
            idx.commit()
        idx.close()


run_script(main)

