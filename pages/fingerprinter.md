Title: Fingerprinter

<div class="rightimg">

![Screenshot](/static/fingerprinter-gnome-small.png)

</div>

Acoustid fingerprinter is a cross-platform GUI application that uses
[Chromaprint][chp] to submit audio fingerprints from your music collection
to the Acoustid database. Only tagged audio files are submitted. Files
tagged by MusicBrainz applications such as [Picard][picard] or [Jaikoz][jaikoz]
are preferred, but it will submit fingerprints for any files that have tags
such as track title, artist name, album name, etc.

[chp]: /chromaprint
[picard]: http://musicbrainz.org/doc/Picard
[jaikoz]: http://www.jthink.net/jaikoz/

### Download

Latest release &mdash; 0.4 (Aug 6, 2011)

 * [Source code][src]
 * Packages
     * [Windows][win]
     * [Mac OS X][osx]
     * [Arch Linux](http://aur.archlinux.org/packages.php?ID=46359)
     * [Debian](http://packages.debian.org/acoustid-fingerprinter)
     * [Gentoo](http://proaudio.tuxfamily.org/wiki/index.php?title=Usage) (Pro-Audio Gentoo overlay)
     * [Ubuntu][ppa]

[src]: https://github.com/downloads/lalinsky/acoustid-fingerprinter/acoustid-fingerprinter-0.4.tar.gz
[win]: https://github.com/downloads/lalinsky/acoustid-fingerprinter/acoustid-fingerprinter-0.4-win32.zip
[osx]: https://github.com/downloads/lalinsky/acoustid-fingerprinter/acoustid-fingerprinter-0.4-mac.dmg
[ppa]: https://launchpad.net/~luks/+archive/acoustid

### Alternatives

There are other applications that can submit fingerprints to the Acoustid database.
You can use them instead of the Acoustid fingerprinter to contribute:

 * [Jaikoz][jaikoz]
 * [Quod Libet][ql] with this [plugin][qlp]

[ql]: http://code.google.com/p/quodlibet/
[qlp]: http://code.google.com/p/quodlibet/source/browse/plugins/songsmenu/fingerprint.py

### Development

You can dowload the development version of the source code from [GitHub][gh].
Either you can use [Git][git] to clone the repository or download a
zip/tar.gz file with the latest version.

The source code is licensed under the [GPL2+ license][gpl].

[gpl]: http://www.gnu.org/licenses/gpl-2.0.html
[gh]: https://github.com/lalinsky/acoustid-fingerprinter
[git]: http://git-scm.com/
