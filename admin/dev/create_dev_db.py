#!/usr/bin/env python

import os
import alembic
import alembic.config
import sqlalchemy
import sqlalchemy.orm
from acoustid.tables import metadata
from acoustid.script import run_script
from mbdata.sample_data import create_sample_data


def main(script, opts, args):
    with script.engine.connect() as conn:
        with conn.begin():
            if opts.drop:
                old_metadata = sqlalchemy.MetaData(conn)
                old_metadata.reflect()
                old_metadata.reflect(schema='musicbrainz')
                old_metadata.drop_all(checkfirst=False)
            if opts.create:
                metadata.create_all(conn)
                if not opts.empty:
                    session = sqlalchemy.orm.Session(conn, autoflush=True)
                    create_sample_data(session)
        if opts.create:
            alembic_cfg = alembic.config.Config(os.path.join(os.path.dirname(__file__), "..", "..", "alembic.ini"))
            alembic.command.stamp(alembic_cfg, "head")


def add_options(parser):
    parser.add_option("-D", "--drop", action="store_true", default=False)
    parser.add_option("-C", "--create", action="store_true", default=False)
    parser.add_option("-E", "--empty", action="store_true", default=False)


run_script(main, add_options)
