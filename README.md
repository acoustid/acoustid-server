AcoustID Server
===============

This software is only meant to run on [acoustid.org](https://acoustid.org). Running it on your own server is not supported.
It's possible, but you need to understand the system well enough and even then it's probably not going to be useful to you.

Local Development
-----------------

You need Python 3.12 or newer to run the code. On Ubuntu, you can install the required
packages using the following command:

    sudo apt install python3 python3-dev python3-venv

You also need uv, see their [installation instructions](https://docs.astral.sh/uv/getting-started/installation/).

Setup Python virtual environment:

    uv sync
    source .venv/bin/activate

Start the required services using Docker:

    export COMPOSE_FILE=docker-compose.yml:docker-compose.localhost.yml

    docker compose up -d redis postgres index

Prepare the configuration file:

    cp acoustid.conf.dist acoustid.conf
    vim acoustid.conf

Initialize the local database:

    alembic upgrade head

Run the applications:

    aserver run web
    aserver run api
    aserver run cron
    aserver run worker

Local Testing
-------------

You can use the provided `docker-compose.yml` file to quickly set up a test environment:

    export COMPOSE_DOCKER_CLI_BUILD=1
    export DOCKER_BUILDKIT=1
    export COMPOSE_FILE=docker-compose.yml:docker-compose.localhost.yml
    export COMPOSE_PROFILES=frontend,backend

    docker compose up -d

Database migrations
-------------------

Upgrading the database schema online:

    alembic upgrade head

Upgrading the database schema offline:

    alembic upgrade <previous-rev>:head --sql

Generating a new database schema change:

    alembic revision --autogenerate -m "my message"

Unit tests
----------

Before you can run the test suite, you need to create a configuration file
called acoustid-test.conf. This should use a separate database from the
one you use for development, but it should have the same structure.

You can then run the test suite like this:

    pytest -v tests/

The first thing it does is setting up the database. Normally you shouldn't
need to do this more than once, so the next time you can run the test suite
without the database setup code:

    SKIP_DB_SETUP=1 pytest -v tests/
