#!/usr/bin/env bash

set -e

ADMINDIR=`dirname $0`
eval `$ADMINDIR/dumpconfig.py $ADMINDIR/../conf/acoustid.xml`


CREATEDB=0
DROPDB=0
while getopts cd name
do
    case $name in
    c)	CREATEDB=1;;
    d)  DROPDB=1;;
    \?) printf "Usage: %s: [-c] [-d]\n" $0
		printf "  -d	Drop existing database\n"
		printf "  -c	Create the database before importing the structure\n"
        exit 2;;
    esac
done

PSQL=$ADMINDIR/psql.sh

function install_contrib_module {
	FILENAME=`pg_config --sharedir`/contrib/$1.sql
	if [ ! -f $FILENAME ]; then
		echo "PostgreSQL extension $NAME ($FILENAME) not found" 1>&2
		exit 1
	fi
	$PSQL <$FILENAME
}

if [ $DROPDB -eq 1 ]; then
	echo "DROP DATABASE $DB_NAME;" | psql -U postgres -h $DB_HOST -p $DB_PORT -e
fi;

if [ $CREATEDB -eq 1 ]; then
	echo "CREATE DATABASE $DB_NAME WITH OWNER $DB_USER;" | psql -U postgres -h $DB_HOST -p $DB_PORT -e
	echo "CREATE LANGUAGE plpgsql;" | psql -U postgres -h $DB_HOST -p $DB_PORT $DB_NAME -e
fi;

install_contrib_module _int
install_contrib_module acoustid
$PSQL -e <$ADMINDIR/sql/CreateTables.sql
$PSQL -e <$ADMINDIR/sql/CreatePrimaryKeys.sql
$PSQL -e <$ADMINDIR/sql/CreateFunctions.sql
$PSQL -e <$ADMINDIR/sql/CreateFKConstraints.sql
$PSQL -e <$ADMINDIR/sql/CreateIndexes.sql

