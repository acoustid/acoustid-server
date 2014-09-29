Title: Fingerprinter

<div class="rightimg">

![Screenshot](/static/fingerprinter-gnome-small.png)

</div>

AcoustID fingerprinter is a cross-platform GUI application that uses
[Chromaprint][chp] to submit audio fingerprints from your music collection
to the AcoustID database. Only tagged audio files are submitted. Files
tagged by MusicBrainz applications such as [Picard][picard] or [Jaikoz][jaikoz]
are preferred, but it will submit fingerprints for any files that have tags
such as track title, artist name, album name, etc.

[chp]: /chromaprint
[picard]: http://musicbrainz.org/doc/Picard
[jaikoz]: http://www.jthink.net/jaikoz/

### Download

Latest release &mdash; 0.6 (Sep 5, 2012)

 * [Source code][src]
 * Packages
     * [Windows][win]
     * [Mac OS X][osx]
     * [Arch Linux](https://aur.archlinux.org/packages/acoustid-fingerprinter/)
     * [Debian](http://packages.debian.org/acoustid-fingerprinter)
     * [Gentoo](http://proaudio.tuxfamily.org/wiki/index.php?title=Usage) (Pro-Audio Gentoo overlay)
     * [Ubuntu][ppa]

[src]: https://bitbucket.org/acoustid/acoustid-fingerprinter/downloads/acoustid-fingerprinter-0.6.tar.gz
[win]: https://bitbucket.org/acoustid/acoustid-fingerprinter/downloads/acoustid-fingerprinter-0.5-win32.zip
[osx]: https://bitbucket.org/acoustid/acoustid-fingerprinter/downloads/acoustid-fingerprinter-0.5-mac.dmg
[ppa]: https://launchpad.net/~luks/+archive/acoustid

### Alternatives

There are other applications that can submit fingerprints to the AcoustID database.
You can use them instead of the AcoustID fingerprinter to contribute:

 * [Picard][picard]
 * [Jaikoz][jaikoz]
 * [Puddletag][Puddletag]
 * [Quod Libet][ql] with this [plugin][qlp]
 * [Beets][beets] with this [plugin][beetschroma]

[ql]: http://code.google.com/p/quodlibet/
[qlp]: http://code.google.com/p/quodlibet/source/browse/plugins/songsmenu/fingerprint.py
[puddletag]: http://puddletag.sourceforge.net/
[beets]: http://beets.radbox.org/
[beetschroma]: http://beets.readthedocs.org/en/latest/plugins/chroma.html

### Development

You can dowload the development version of the source code from [Bitbucket][bb].
Either you can use [Git][git] to clone the repository or download a
zip/tar.gz file with the latest version.

The source code is licensed under the [GPL2+ license][gpl].

[gpl]: http://www.gnu.org/licenses/gpl-2.0.html
[bb]: https://bitbucket.org/acoustid/acoustid-fingerprinter
[git]: http://git-scm.com/
