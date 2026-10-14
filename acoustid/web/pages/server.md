Title: Server

The AcoustID server is a set of applications written in Python: this website,
the [web service](/webservice) that applications use to look up and submit
fingerprints, and background workers that import submissions and keep the
statistics up to date. The data is stored in PostgreSQL.

Fingerprint searches go to [acoustid-index][index], a custom index server
designed specifically for searching audio fingerprints.

The source code is licensed under the [MIT License][mit]. You can download it
from [GitHub][gh].

[mit]: https://opensource.org/licenses/MIT
[gh]: https://github.com/acoustid/acoustid-server
[index]: https://github.com/acoustid/acoustid-index
