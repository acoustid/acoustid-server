AcoustID Server
===============

This software is only meant to run on [acoustid.org](https://acoustid.org). Running it on your own server is not supported.
It's possible, but you need to understand the system well enough and even then it's probably not going to be useful to you.

Installation
------------

On Ubuntu you can install all dependencies using the following commands (as root):

    sudo apt-get install python python-dev python-virtualenv

Start the required services using Docker:

    docker-compose up -d

If you can't use Docker, you will need to install PostgreSQL and Redis from packages:

    sudo apt-get install postgresql postgresql-contrib
    sudo apt-get install redis-server

And you will also neeed to compile the [pg\_acoustid](https://bitbucket.org/acoustid/pg_acoustid) extension yourself. It's easier to use the ready-made Docker images.

Setup Python virtual environment:

    virtualenv e
    source e/bin/activate
    pip install -r requirements.txt
    pip install -r requirements_dev.txt

Prepare the configuration file:

    cp acoustid.conf.dist acoustid.conf
    vim acoustid.conf

Create the PostgreSQL database:

    sudo -u postgres createuser acoustid
    sudo -u postgres createdb -O acoustid acoustid

Install extensions into the newly created database:

    sudo -u postgres psql acoustid -c 'CREATE EXTENSION intarray;'
    sudo -u postgres psql acoustid -c 'CREATE EXTENSION pgcrypto;'
    sudo -u postgres psql acoustid -c 'CREATE EXTENSION acoustid;'

Create the database structure:

    ./run_psql.sh <sql/CreateTables.sql
    ./run_psql.sh <sql/CreatePrimaryKeys.sql
    ./run_psql.sh <sql/CreateFKConstraints.sql
    ./run_psql.sh <sql/CreateIndexes.sql

Setup a MusicBrainz slave database (without custom extensions):

    cd /path/to/mbslave
    cp mbslave.conf.default mbslave.conf
    vim mbslave.conf
    echo 'CREATE SCHEMA musicbrainz;' | ./mbslave-psql.py
    sed 's/cube/text/i' sql/CreateTables.sql | ./mbslave-psql.py
    ./mbslave-import.py mbdump.tar.bz2 mbdump-derived.tar.bz2
    ./mbslave-psql.py <sql/CreatePrimaryKeys.sql
    vim sql/CreateFunctions.sql # remove functions that mention "cube"
    ./mbslave-psql.py <sql/CreateFunctions.sql
    grep -vE '(collate|page_index|gist)' sql/CreateIndexes.sql | ./mbslave-psql.py
    ./mbslave-psql.py <sql/CreateViews.sql
    ./mbslave-psql.py <sql/CreateSimpleViews.sql
    ./mbslave-sync.py

TODO


Local Testing
-------------

You can use the provided `docker-compose.yml` file to quickly set up a test environment:

    export COMPOSE_DOCKER_CLI_BUILD=1
    export DOCKER_BUILDKIT=1
    export COMPOSE_FILE=docker-compose.yml:docker-compose.localhost.yml
    export COMPOSE_PROFILES=frontend,backend

    docker-compose up -d

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

    nosetests -v

The first thing it does is setting up the database. Normally you shouldn't
need to do this more than once, so the next time you can run the test suite
without the database setup code:

    SKIP_DB_SETUP=1 nosetests -v
