#!/usr/bin/env python

# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

from acoustid.script import run_script
import subprocess


def main(script, opts, args):
    subprocess.call(['psql'] + script.config.database.create_psql_args())

run_script(main)

