#!/usr/bin/env python

from sqlalchemy import MetaData
from acoustid.script import run_script


def main(script, opts, args):
    from acoustid.tables import metadata
    with script.engine.connect() as conn:
        with conn.begin():
            if opts.drop:
                old_metadata = MetaData(conn)
                old_metadata.reflect()
                old_metadata.drop_all()
            if opts.create:
                metadata.create_all(conn)


def add_options(parser):
    parser.add_option("-D", "--drop", action="store_true", default=False)
    parser.add_option("-C", "--create", action="store_true", default=False)


run_script(main, add_options)
