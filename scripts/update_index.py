#!/usr/bin/env python

# Copyright (C) 2011-2012 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

from contextlib import closing
from acoustid.script import run_script
from acoustid.data.fingerprint import update_fingerprint_index


def main(script, opts, args):
    with closing(script.db_engines['app'].connect()) as db:
        update_fingerprint_index(db, script.index)


run_script(main)

