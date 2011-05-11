Title: Roadmap

This page lists a number of goals that need to be done or would be nice to
have. If you would like to help with any of these goals, please [let me know][1]

[1]:http://groups.google.com/group/acoustid

### Short-term Goals

* Write Python scripts to maintain the fingerprint database, generate reports
  (remove obviously wrong fingerprints, merge incorrectly imported
  fingerprints, etc.).<br />
  **Status:** No work done on this yet.
* Run a test to determine the best fingerprint similarity thresholds based on
  [NGS][2] recordings. The final test probably needs to wait until NGS
  data is somehow stabilized, but it can be prepared before that.<br />
  **Status:** No work done on this yet.
* Allow browsing of the fingerprint database on the website.<br />
  **Status:** No work done on this yet.
* Create a Greasemonkey script and corresponding API to show fingerprints on
  the MusicBrainz website, similarly to PUIDs.<br />
  **Status:** No work done on this yet.
* Modify MusicBrainz Picard to optionally use Acoustid for lookups.<br />
  **Status:** Very crude hack implemented ([code][4]), needs work.
* Write a custom server application for fingerprint search.<br />
  **Status:** Proof-of-concept implemented ([code][3]), needs a lot of work.

[3]: https://github.com/lalinsky/acoustid-index
[2]: http://wiki.musicbrainz.org/Next_Generation_Schema 
[4]: https://code.launchpad.net/~luks/picard/acoustid

### Future Goals / Research Areas

* Put whole fingerprints into the index, allow searching for audio snippets. The
  intended use for this is tracklisting of streams that are compilations of
  multiple tracks (internet radio, DJ-mix).
* Research possible improvements to the fingerprint algorithm without
  degrading recording-level identification functionality.

