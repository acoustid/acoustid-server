Title: Server

AcoustID server is a web application written in Python. It consists of this
website and handlers for the [web service](/webservice), which allow users
to look up and submit fingerprints.

Fingerprint lookups are currently implemented using [PostgreSQL GIN indexes][gin],
but there are plans to implement a custom special-purpose index server for
more efficient searches.

The source code is licensed under the [MIT License][mit]. You can dowload it
from from [Bitbucket][bb].

[mit]: http://creativecommons.org/licenses/MIT/
[bb]: https://bitbucket.org/acoustid/acoustid-server
[gin]: http://developer.postgresql.org/pgdocs/postgres/gin.html
[bb-index]: https://bitbucket.org/acoustid/acoustid-index

