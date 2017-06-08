Title: Chromaprint

Chromaprint is the core component of the AcoustID project. It's a client-side
library that implements a custom algorithm for extracting fingerprints from
any audio source. Overview of the fingerprint extraction process can be
found in the blog post ["How does Chromaprint work?"][blog2].

{% if release %}

### Download

Latest release &mdash; {{ release.name | replace('Chromaprint', '') }} ({{ release.published_at[:10] }})

{% for asset in release.assets %}
* [{{ asset.name }}]({{ asset.browser_download_url }}) ({{ asset.size | filesizeformat }})
{%- endfor %}

Most Linux distributions also have their own packages for Chromaprint.

You can find downloads for older releases on [GitHub](https://github.com/acoustid/chromaprint/releases).

{% endif %}

### Usage

The library exposes a simple C API. The documentation for the C API can be found in [chromaprint.h](https://github.com/acoustid/chromaprint/blob/master/src/chromaprint.h).

Note that the library only calculates audio fingerprints from the provided
raw uncompressed audio data. It does not deal with audio file formats in
any way. Your application needs to find a way to decode audio files
(MP3, MP4, FLAC, etc.) and feed the uncompressed data to Chromaprint.

You can use [pyacoustid](https://pypi.python.org/pypi/pyacoustid) to interact with the library from Python.
It provides a direct wrapper around the library, but also higher-level functions for generating fingerprints from audio files.

You can also use the fpcalc utility programatically. It can produce JSON output, which should be easy to parse in any language.
This is the recommended way to use Chromaprint if all you need is generate fingerprints for AcoustID.

### Development

You can dowload the development version of the source code from [GitHub](https://github.com/acoustid/chromaprint).
Either you can use [Git][git] to clone the repository or download a
zip/tar.gz file with the latest version.

You will need a C++ compiler and [CMake](https://cmake.org/) to build the library. [FFmpeg](https://ffmpeg.org/) is required to build the fpcalc tool.

    $ git clone https://github.com/acoustid/chromaprint.git
	$ cd chromaprint
	$ cmake .
	$ make

See the [README](https://github.com/acoustid/chromaprint/blob/master/README.md) file for more details on building the library.

[blog1]: http://oxygene.sk/lukas/2010/07/introducing-chromaprint/
[blog2]: https://oxygene.sk/2011/01/how-does-chromaprint-work/
[git]: http://git-scm.com/
