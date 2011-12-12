#!/usr/bin/env python

# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

from acoustid.script import run_script
import os


def main(script, opts, args):
    os.execlp('psql', 'psql', *(script.config.database.create_psql_args() + args))

run_script(main)

