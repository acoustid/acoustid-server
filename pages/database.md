Title: Database

The Acoustid database includes user-submitted audio fingerprints, their mapping to
MusicBrainz IDs and some supporting tables. It follows the [structure of the
PostgreSQL database][sql] used by the Acoustid server. Each table is exported in a
separate file with the tab-separated text format used by the 
[`COPY` command][copy]. At the moment, there are no tools for importing the
database dump, it has to be done manually.

The main database is licensed under the [Creative Commons Attribution-ShareAlike 3.0
Unported License][cc], with the exception of the MusicBrainz-AcoustID mapping which is
placed into the [public domain][pd].

Monthly database dumps can be downloaded [here](http://acoustid.org/data/).

All files are signed using [GnuPG](gpg). In order to verify the signatures you have
to first import the [public key](pubkey):

    $ curl http://acoustid.org/data/pubkey.txt | gpg --import -

Once you have the public key imported, you can verify the signature:

    $ gpg --verify acoustid-core-dump.tar.bz2.asc
    gpg: Signature made Sun Nov 20 10:17:24 2011 UTC using RSA key ID B8ED25DD
    gpg: Good signature from "AcoustID Downloads <downloads@acoustid.org>"

[copy]: http://www.postgresql.org/docs/9.0/static/sql-copy.html
[cc]: http://creativecommons.org/licenses/by-sa/3.0/
[pd]: http://creativecommons.org/licenses/publicdomain/
[sql]: https://github.com/lalinsky/acoustid-server/blob/master/sql/CreateTables.sql
[gpg]: http://www.gnupg.org/
[pubkey]: http://acoustid.org/data/pubkey.txt