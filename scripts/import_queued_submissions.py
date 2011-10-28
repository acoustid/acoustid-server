#!/usr/bin/env python

# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

from acoustid.script import run_script
from acoustid.data.submission import import_queued_submissions


def main(script, opts, args):
    conn = script.engine.connect()
    import_queued_submissions(conn, limit=300, index=script.index)

run_script(main)

