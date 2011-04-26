Title: Chromaprint

Chromaprint is the core component of the Acoustid project. It's a client-side
library that implements a custom algorithm for extracting fingerprints from
any audio source. Overview of the fingerprint extraction process can be
found in the blog post ["How does Chromaprint work?"][blog2].

The library exposes a simple [C API][api] and the package also included
bindings for the Python language.

### Download

Latest release &mdash; 0.2 (Jan 29, 2011)

 * [Source code tarball](...)
 * Packages
     * [Ubuntu][ppa] ([daily builds][ppad])
     * [Arch Linux](http://aur.archlinux.org/packages.php?ID=46382)
     * [FreeBSD](https://github.com/lalinsky/ports)

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
[ppa]: https://launchpad.net/~luks/+archive/acoustid
[ppad]: https://launchpad.net/~luks/+archive/acoustid-daily
[git]: http://git-scm.com/
[fftw]: http://www.fftw.org/
[ffmpeg]: http://www.ffmpeg.org/
[vdsp]: http://developer.apple.com/library/mac/#documentation/Performance/Conceptual/vDSP_Programming_Guide/Introduction/Introduction.html
[taglib]: http://developer.kde.org/~wheeler/taglib.html
[boost]: http://www.boost.org/
[gtest]: http://code.google.com/p/googletest/

