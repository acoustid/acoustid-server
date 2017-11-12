AcoustID Server
===============

This software is only meant to run on [acoustid.org](https://acoustid.org). Running it on your own server is not supported.
It's possible, but you need to understand the system well enough and even then it's probably not going to be useful to you.

Installation
------------

On Ubuntu you can install all dependencies using the following commands (as root):

    sudo apt-get install postgresql postgresql-contrib
    sudo apt-get install redis-server
    sudo apt-get install python python-dev python-virtualenv

You will also need one custom PostgreSQL extension:

    echo "deb http://deb.oxygene.sk/ubuntu `lsb_release -c -s` main" | sudo tee /etc/apt/sources.list.d/oxygene.list
    sudo apt-get update
    sudo apt-get install postgresql-9.X-acoustid

(You can also compile it yourself from [sources](https://bitbucket.org/acoustid/pg_acoustid).)

Setup Python virtual environment:

    virtualenv e
    source e/bin/activate
    pip install -r requirements.txt

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


Development
-----------

You can use the provided `Vagrantfile` to quickly set up a development instance:

    vagrant up
    vagrant ssh

Create an empty database:

    ./admin/dev/create_dev_db.py -c acoustid.conf --drop --create

You can start the web application like this:
 
    ./run_web.sh --host=0.0.0.0

If you want to test it with HTTP enabled, use this:

    ./run_web.sh --ssl

Then setup forwarding from the standard HTTPS port 443 to the application port:

    sudo redir --lport=443 --cport=5000

Add `127.0.0.1 acoustid.org` to your `/etc/hosts` file and then you can see the
development version of the application at https://acoustid.org.

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
