#!/usr/bin/env python

from sqlalchemy.schema import CreateIndex, DropIndex, AddConstraint, DropConstraint, CreateTable, DropTable
from acoustid.script import run_script

def dump_ddl(items, name, func, engine):
    with open('sql/{}.sql'.format(name), 'w') as sql:
        for item in items:
            sql.write('{};\n'.format(str(func(item).compile(engine)).strip()))


def main(script, opts, args):
    from acoustid.tables import metadata

    indexes = []
    for table in metadata.tables.values():
        if table.schema != "musicbrainz":
            indexes.extend(table.indexes)
    indexes.sort(key=lambda i: (i.table.name, i.name))
    dump_ddl(indexes, 'CreateIndexes', CreateIndex, script.engine)
    dump_ddl(reversed(indexes), 'DropIndexes', DropIndex, script.engine)

    primary_keys = []
    for table in metadata.tables.values():
        if table.schema != "musicbrainz":
            primary_keys.append(table.primary_key)
    primary_keys.sort(key=lambda i: (i.table.name, i.name))
    dump_ddl(primary_keys, 'CreatePrimaryKeys', AddConstraint, script.engine)
    dump_ddl(reversed(primary_keys), 'DropPrimaryKeys', DropConstraint, script.engine)

    foreign_keys = []
    for table in metadata.tables.values():
        if table.schema != "musicbrainz":
            foreign_keys.extend(table.foreign_key_constraints)
    foreign_keys.sort(key=lambda i: (i.table.name, i.name))
    dump_ddl(foreign_keys, 'CreateFKConstraints', AddConstraint, script.engine)
    dump_ddl(reversed(foreign_keys), 'DropFKConstraints', DropConstraint, script.engine)

    tables = []
    for table in metadata.tables.values():
        if table.schema != "musicbrainz":
            tables.append(table)
    tables.sort(key=lambda i: i.name)
    dump_ddl(tables, 'CreateTables', CreateTable, script.engine)
    dump_ddl(reversed(tables), 'DropTables', DropTable, script.engine)


def add_options(parser):
    pass


run_script(main, add_options)
