Title: Roadmap

This page lists a number of goals that need to be done or would be nice to
have. If you would like to help with any of these goals, please [let me know][1]

[1]:http://groups.google.com/group/acoustid

### Short-term Goals

* Write Python scripts to maintain the fingerprint database, generate reports
  (remove obviously wrong fingerprints, merge incorrectly imported
  fingerprints, etc.).<br />
  **Status:** No work done on this yet.
* Allow better browsing of the fingerprint database on the website.<br />
  **Status:** No work done on this yet.
* Display AcoustIDs on the MusicBrainz website. <br />
  **Status:** Implemented as an [userscript](http://userscripts.org/scripts/show/110183), but should be integrated to the MusicBrainz server code. Needs agreement from MusicBrainz.
* Allow MusicBrainz users to submit edits to remove incorrect AcoustID-MusicBrainz matches.<br />
  **Status:** No work done on this yet. Needs agreement from MusicBrainz.
* Modify MusicBrainz Picard to optionally (exclusively?) use Acoustid for lookups.<br />
  **Status:** Very crude hack implemented ([code][4]). Needs work.

[3]: https://github.com/lalinsky/acoustid-index
[2]: http://wiki.musicbrainz.org/Next_Generation_Schema 
[4]: https://code.launchpad.net/~luks/picard/acoustid

### Future Goals / Research Areas

* Put whole fingerprints into the index, allow searching for audio snippets. The
  intended use for this is tracklisting of streams that are compilations of
  multiple tracks (internet radio, DJ-mix).
* Research possible improvements to the fingerprint algorithm without
  degrading recording-level identification functionality.

