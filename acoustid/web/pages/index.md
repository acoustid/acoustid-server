Title: Welcome to AcoustID!

AcoustID is a project providing complete audio identification
service, based entirely on open source software.

It consists of a [client library][chromaprint] for generating
compact fingerprints from audio files, a large crowd-sourced
[database of audio fingerprints][db], many of which are linked
to the [MusicBrainz][mb] metadata
database using their [unique identifiers][mbid], and an [web service][webservice]
that enables applications to quickly search in the fingerprint database.

<div class="row">

<div class="col-sm-6">
<h3>Users</h3>

<p>
    If you have an unknown music file, one of the applications using
    AcoustID will very likely be able to tell you what song it is,
    who wrote it, and a lot more. In case AcoustID doesn't recognize
    the song yet, you can help by submitting it to the database, so
    that the next person trying to identify the same song will
    have more luck.
</p>

<ul class="list-nopadding">
    <li><a href="/applications">Browse applications that use AcoustID</a></li>
    <li><a href="/api-key">Get user API key for submitting new fingerprints</a></li>
</ul>


</div>

<div class="col-sm-6">
<h3>Developers</h3>

<p>
    If you are developing an application that needs to identify
    unknown audio files, you can use AcoustID to help with that.
    The service is completely free for non-commercial applications,
    all you need to do is register your application.
    You can also use the service in commercial applications via
    <a href="https://acoustid.biz">AcoustID OÜ</a>.
</p>

<ul class="list-nopadding">
    <li><a href="/webservice">Read the API documentation</a></li>
    <li><a href="/new-application">Register your application</a></li>
    <li><a href="/my-applications">View your registered applications</a></li>
</ul>

</div>

</div>

[db]: flask:general.database
[chromaprint]: flask:general.chromaprint
[webservice]: flask:general.webservice
[mb]: //musicbrainz.org/
[mbid]: //musicbrainz.org/doc/MusicBrainz_Identifier
