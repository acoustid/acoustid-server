#!/usr/bin/env python

from acoustid.script import run_script


def main(script, opts, args):
    from acoustid.tables import metadata
    with script.engine.connect() as conn:
        with conn.begin():
            metadata.create_all(conn)


run_script(main)
