#!/usr/bin/env python

from sqlalchemy import MetaData
from acoustid.script import run_script


def main(script, opts, args):
    from acoustid.tables import metadata
    with script.engine.connect() as conn:
        with conn.begin():
            old_metadata = MetaData(conn)
            old_metadata.reflect()
            old_metadata.drop_all()
#            metadata.create_all(conn)


run_script(main)
