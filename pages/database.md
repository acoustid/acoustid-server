Title: Database

The Acoustid database includes user-submitted audio fingerprints, their mapping to
MusicBrainz IDs and some supporting tables. It follows the [structure of the
PostgreSQL database][sql] used by the Acoustid server. Each table is exported in a
separate file with the tab-separated text format used by the 
[`COPY` command][copy]. At the moment, there are no tools for importing the
database dump, it has to be done manually.

The database is licensed under the [Creative Commons Attribution-ShareAlike 3.0
Unported License][cc].

Monthly database dumps can be downloaded at [here](http://acoustid.org/data/).

[copy]: http://www.postgresql.org/docs/9.0/static/sql-copy.html
[cc]: http://creativecommons.org/licenses/by-sa/3.0/
[sql]: https://github.com/lalinsky/acoustid-server/blob/master/sql/CreateTables.sql
