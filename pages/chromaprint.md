Title: Chromaprint

Chromaprint is the core component of the Acoustid project. It's a client-side
library that implements a custom algorithm for extracting fingerprints from
any audio source. Overview of the fingerprint extraction process can be
found in the blog post ["How does Chromaprint work?"][blog2].

### Download

Latest release &mdash; 0.4 (May 14, 2011)

 * [Source code tarball](https://github.com/downloads/lalinsky/chromaprint/chromaprint-0.4.tar.gz) (529K)
 * Packages
     * [Arch Linux](http://aur.archlinux.org/packages.php?ID=46382)
     * [Debian](http://packages.debian.org/search?suite=default&section=all&arch=any&searchon=names&keywords=chromaprint)
     * [FreeBSD](https://github.com/lalinsky/ports)
     * [Ubuntu][ppa] ([daily builds][ppad])
 * Static binaries for the fpcalc tool
     * [Windows, x86](https://github.com/downloads/lalinsky/chromaprint/chromaprint-fpcalc-0.4-win32.zip) (633K)
     * [Mac OS X, x86, 10.4+](https://github.com/downloads/lalinsky/chromaprint/chromaprint-fpcalc-0.4-osx.tar.gz) (523K)
     * [Linux, x86](https://github.com/downloads/lalinsky/chromaprint/chromaprint-fpcalc-0.4-linux.tar.gz) (650K)

[ppa]: https://launchpad.net/~luks/+archive/acoustid
[ppad]: https://launchpad.net/~luks/+archive/acoustid-daily

### Usage

The library exposes a simple C API and the package also includes
bindings for the Python language. The documentation for the C API
can be found in the [main header file][api].

Note that the library only calculates audio fingerprints from the provided
raw uncompressed audio data. It does not deal with audio file formats in
any way. Your application needs to find a way to decode audio files
(MP3, MP4, FLAC, etc.) and feed the uncompressed data to Chromaprint.

There is a simple [Python example][pyexample] that calculates fingerprints
from WAV files and a less simple, but more useful [C example][cexample] that uses
FFmpeg to calculate fingerprints from any audio files.

[pyexample]: https://github.com/lalinsky/chromaprint/blob/master/python/examples/fpwav.py
[cexample]: https://github.com/lalinsky/chromaprint/blob/master/examples/fpcalc.c

### Development

You can dowload the development version of the source code from [GitHub][gh].
Either you can use [Git][git] to clone the repository or download a
zip/tar.gz file with the latest version.

In order to just compile the library, you will need to have either
[FFTW3][fftw] or [FFmpeg][ffmpeg] installed, unless you are on OS X,
where we can use the standard [vDSP][vdsp] library.
If you want to build the full package, you will also need
[TagLib][taglib], [Boost][boost] and [Google Test][gtest].

    $ git clone git://github.com/lalinsky/chromaprint.git
	$ cd chromaprint
	$ cmake .
	$ make

The source code is licensed under the [LGPL2.1+ license][lgpl].

[lgpl]: http://www.gnu.org/licenses/lgpl-2.1.html
[blog1]: http://oxygene.sk/lukas/2010/07/introducing-chromaprint/
[blog2]: http://oxygene.sk/lukas/2011/01/how-does-chromaprint-work/
[api]: https://github.com/lalinsky/chromaprint/blob/master/src/chromaprint.h
[gh]: https://github.com/lalinsky/chromaprint
[git]: http://git-scm.com/
[fftw]: http://www.fftw.org/
[ffmpeg]: http://www.ffmpeg.org/
[vdsp]: http://developer.apple.com/library/mac/#documentation/Performance/Conceptual/vDSP_Programming_Guide/Introduction/Introduction.html
[taglib]: http://developer.kde.org/~wheeler/taglib.html
[boost]: http://www.boost.org/
[gtest]: http://code.google.com/p/googletest/

