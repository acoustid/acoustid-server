Title: Welcome to AcoustID!

AcoustID is an open source project that provides free audio
file identification service to many open source applications. 
It that consists of a large crowd-sourced database of audio
fingerprints, many of which are linked to the [MusicBrainz][] metadata
database using their [unique identifiers][MBID], and an open source
service for managing and searching in the fingerprint database.

### Ok, how can I use it?

If you have an unknown music file, one of the applications using
AcoustID will very likely be able to tell you what song is it,
who wrote it, and a lot more. In case AcoustID doesn't recognize
the song yet, you can submit it to the database, so that the next
person trying to identify the same song will have more luck.

If you are an appliation developer, please have a look at our
developers page.

open source project that aims to create a
free database of audio fingerprints with mapping to the [MusicBrainz][5]
metadata database and provide a [web service][6] for audio file
identification using this database.

### I'm a developer, how can I integrate this into my application?

The content of the database is all submitted by users. You can contribute
by downloading our [submission tool][4] and letting it to analyze your
music collection. It will submit fingerprints along with some metadata
necessary to identify the songs to the AcoustID database.

All software components are open source, so if you are a developer
interested in the project, you can download the source code for the
[client library][3], the [server application][2] and also the [database][1]
itself.

[1]: /database
[2]: /server
[3]: /chromaprint
[4]: /fingerprinter
[6]: /webservice
[MusicBrainz]: //musicbrainz.org/
[MBID]: //musicbrainz.org/doc/MusicBrainz_Identifier
