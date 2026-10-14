Title: About the AcoustID project

AcoustID is a project providing a complete audio identification service,
based entirely on open source software.

It consists of a [client library](/chromaprint) for generating compact
fingerprints from audio files, a large crowd-sourced
[database of audio fingerprints](/database), many of which are linked to the
[MusicBrainz][mb] metadata database using their [unique identifiers][mbid],
and a [web service](/webservice) that enables applications to quickly search
in the fingerprint database.

{% if stats.fingerprints >= 1000000 %}
Today the database holds over {{ (stats.fingerprints // 1000000) }} million
fingerprints, grouped into more than {{ (stats.tracks // 1000000) }} million
AcoustIDs{% if stats.contributors >= 1000000 %}, submitted by over
{{ (stats.contributors // 1000000) }} million contributors{% endif %}.
{% if stats.applications >= 1000 %}Over {{ (stats.applications // 1000) }} thousand
applications are registered to use the web service{% if stats.lookups >= 1000000 %},
which answers around {{ (stats.lookups / 1000000)|round|int }} million lookups
a day{% endif %}. {% endif %}See the [statistics](/stats) for the exact numbers.
{% endif %}

### History

The project was started in 2010 by [Lukáš Lalinský][lukas] as a completely
open source alternative to the proprietary MusicDNS service, which
[MusicBrainz Picard][picard] then used for identifying music files. It was the
first open source audio identification technology and the first large database
of audio fingerprints to be freely available, and today it is used by many
other applications too, such as [beets][beets], MusicBee, FileBot and VLC.
Since 2016, it has been funded by [AcoustID OÜ][biz], which provides the
service to commercial users.

<ol class="timeline">
<li><time>Jul 2010</time><span><a href="https://blog.acoustid.org/posts/introducing-chromaprint/">Chromaprint is introduced</a>, a library for extracting audio fingerprints.</span></li>
<li><time>Aug 2010</time><span><a href="https://blog.acoustid.org/posts/acoustid/">AcoustID is announced</a>. Lookups run on PostgreSQL, using GIN indexes.</span></li>
<li><time>Oct 2010</time><span>The first fingerprint is added to the database, on October 8.</span></li>
<li><time>Dec 2010</time><span>1.1 million submissions so far. The service <a href="https://blog.acoustid.org/posts/acoustid-moved-to-a-new-server/">moves to its own server</a>, and the data becomes available for download.</span></li>
<li><time>Apr 2011</time><span>The server is <a href="https://blog.acoustid.org/posts/new-acoustid-web-service/">rewritten from Java to Python</a>, with a new web service that returns MusicBrainz metadata directly.</span></li>
<li><time>Sep 2011</time><span>Searches move to a dedicated fingerprint index server, <a href="https://github.com/acoustid/acoustid-index">acoustid-index</a>, written in C++.</span></li>
<li><time>Nov 2011</time><span>10 million fingerprints. The service handles over half a million lookups a day.</span></li>
<li><time>Jan 2012</time><span><a href="https://blog.acoustid.org/posts/musicbrainz-acoustid-integration/">MusicBrainz shows AcoustIDs</a> on its recording pages.</span></li>
<li><time>Sep 2014</time><span>25 million fingerprints.</span></li>
<li><time>Oct 2015</time><span><a href="https://blog.acoustid.org/posts/2015-10-08-five-years-of-acoustid/">Five years of AcoustID</a>: 8.3 million MusicBrainz recordings can be identified, and over 100 applications use the service every month.</span></li>
<li><time>Mar 2016</time><span><a href="https://acoustid.biz/">AcoustID OÜ</a> is founded. It offers the service to commercial users, and the income pays for running the service and developing the open source project.</span></li>
<li><time>Feb 2018</time><span>50 million fingerprints.</span></li>
<li><time>Oct 2019</time><span>AcoustID moves to Kubernetes.</span></li>
<li><time>Jan 2021</time><span>75 million fingerprints.</span></li>
<li><time>Mar 2021</time><span>The <a href="https://blog.acoustid.org/posts/2021-03-05-postmortem-of-the-march-2-2021-outage/">worst outage</a> in the project's history: all services are down for three days.</span></li>
<li><time>Jun 2022</time><span>A record 34.9 million lookups in a single day.</span></li>
<li><time>Feb 2025</time><span><a href="https://blog.acoustid.org/posts/2024-12-15-acoustid-will-stop-accepting-fingerprints-without-metadata/">Submissions without metadata are no longer accepted</a>.</span></li>
<li><time>Jan 2026</time><span>90 million fingerprints.</span></li>
<li><time>Aug 2026</time><span>The service moves to a new Kubernetes cluster, and searches switch to a new, much faster generation of acoustid-index, written from scratch in Zig.</span></li>
</ol>

### Get involved

You can help by submitting fingerprints from your music collection,
[contributing to the code][gh], or just spreading the word. Get in touch
through the [contact page](/contact).

[mb]: https://musicbrainz.org/
[mbid]: https://musicbrainz.org/doc/MusicBrainz_Identifier
[lukas]: https://oxygene.sk/
[picard]: https://picard.musicbrainz.org/
[beets]: https://beets.io/
[biz]: https://acoustid.biz/
[gh]: https://github.com/acoustid
