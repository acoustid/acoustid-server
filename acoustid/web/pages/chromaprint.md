Title: Chromaprint

Chromaprint is the core component of the AcoustID project. It's a client-side
library that implements a custom algorithm for extracting fingerprints from
any audio source. Overview of the fingerprint extraction process can be
found in the blog post ["How does Chromaprint work?"][blog2].

### Download

Latest release &mdash; 1.4 (December 3, 2016)

* [Source code tarball](https://bitbucket.org/acoustid/chromaprint/downloads/chromaprint-1.4.tar.gz) (597 KB)
* Static binaries for the `fpcalc` tool
    * [Windows, i686](https://bitbucket.org/acoustid/chromaprint/downloads/chromaprint-fpcalc-1.4-windows-i686.zip) (1.4 MB)
    * [Windows, x86\_64](https://bitbucket.org/acoustid/chromaprint/downloads/chromaprint-fpcalc-1.4-windows-x86_64.zip) (1.5 MB)
    * [macOS, i386](https://bitbucket.org/acoustid/chromaprint/downloads/chromaprint-fpcalc-1.4-macos-i386.tar.gz) (1.1 MB)
    * [macOS, x86\_64](https://bitbucket.org/acoustid/chromaprint/downloads/chromaprint-fpcalc-1.4-macos-x86_64.tar.gz) (1.2 MB)
    * [Linux, i686](https://bitbucket.org/acoustid/chromaprint/downloads/chromaprint-fpcalc-1.4-linux-i686.tar.gz) (1.3 MB)
    * [Linux, x86\_64](https://bitbucket.org/acoustid/chromaprint/downloads/chromaprint-fpcalc-1.4-linux-x86_64.tar.gz) (1.2 MB)
    * [Linux, armhf](https://bitbucket.org/acoustid/chromaprint/downloads/chromaprint-fpcalc-1.4-linux-armhf.tar.gz) (1.2 MB)
* Most Linux distributions have their own binary packages for Chromaprint

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

There is an [example application][cexample] written in C that uses
FFmpeg to calculate fingerprints from any audio files.

[cexample]: https://bitbucket.org/acoustid/chromaprint/src/master/examples/fpcalc.c

### Development

You can dowload the development version of the source code from [Bitbucket][bitbucket].
Either you can use [Git][git] to clone the repository or download a
zip/tar.gz file with the latest version.

In order to just compile the library, you will need to have either
[FFTW3][fftw] or [FFmpeg][ffmpeg] installed, unless you are on OS X,
where we can use the standard [vDSP][vdsp] library.
If you want to build the full package, you will also need
[TagLib][taglib], [Boost][boost] and [Google Test][gtest].

    $ git clone https://bitbucket.org/acoustid/chromaprint.git
	$ cd chromaprint
	$ cmake .
	$ make

The source code is licensed under the [LGPL2.1+ license][lgpl].

[lgpl]: http://www.gnu.org/licenses/lgpl-2.1.html
[blog1]: http://oxygene.sk/lukas/2010/07/introducing-chromaprint/
[blog2]: http://oxygene.sk/lukas/2011/01/how-does-chromaprint-work/
[api]: https://bitbucket.org/acoustid/chromaprint/src/master/src/chromaprint.h
[bitbucket]: https://bitbucket.org/acoustid/chromaprint
[git]: http://git-scm.com/
[fftw]: http://www.fftw.org/
[ffmpeg]: http://www.ffmpeg.org/
[vdsp]: http://developer.apple.com/library/mac/#documentation/Performance/Conceptual/vDSP_Programming_Guide/Introduction/Introduction.html
[taglib]: http://developer.kde.org/~wheeler/taglib.html
[boost]: http://www.boost.org/
[gtest]: http://code.google.com/p/googletest/

