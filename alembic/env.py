from __future__ import with_statement
import os
from alembic import context
from sqlalchemy import engine_from_config, pool
from logging.config import fileConfig

config = context.config
fileConfig(config.config_file_name)

import acoustid.tables
target_metadata = acoustid.tables.metadata

import acoustid.config
acoustid_config = acoustid.config.Config(os.path.join(os.path.dirname(__file__), '..', 'acoustid.conf'))


def include_object(obj, name, type, reflected, compare_to):
    if type == "table" and obj.schema == "musicbrainz":
        return False
    if type == "column" and not obj.table.schema == "musicbrainz":
        return False
    return True


def run_migrations_offline():
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = acoustid_config.database.create_url()
    context.configure(
        url=url, target_metadata=target_metadata, literal_binds=True,
        include_object=include_object)

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = acoustid_config.database.create_engine(poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
