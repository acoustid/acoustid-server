Title: Server

AcoustID server is a web application written in Python. It consists of this
website and handlers for the [web service](/webservice), which allow users
to look up and submit fingerprints.

Fingerprint lookups are currently implemented using [PostgreSQL GIN indexes][gin],
but there are plans to implement a custom special-purpose index server for
more efficient searches.

The source code is licensed under the [MIT License][mit]. You can dowload it
from from [GitHub][gh].

[mit]: http://creativecommons.org/licenses/MIT/
[gh]: https://github.com/lalinsky/acoustid-server
[gin]: http://developer.postgresql.org/pgdocs/postgres/gin.html
[gh-index]: https://github.com/lalinsky/acoustid-index

