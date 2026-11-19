# Copyright (C) 2026 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

"""Delete search log rows once they are older than the retention window.

Shipped with the table rather than added later, deliberately. A retention
policy that arrives after the data does is a policy applied to whatever
happened to accumulate in the meantime, and "we will add cleanup once it
matters" is how a log of what people searched for becomes a permanent record
nobody decided to keep.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from acoustid.data.search_log import delete_old_searches
from acoustid.script import Script

logger = logging.getLogger(__name__)

# Long enough to compare a quarter against the one before it, short enough
# that nothing here becomes a historical archive.
RETENTION_DAYS = 90

# Deleted in bounded batches so this is a series of short transactions rather
# than one long one -- the same cluster is serving the website while it runs.
BATCH_SIZE = 5000

# A backstop, not a limit that is expected to bind. At one batch per
# iteration this is 50M rows, far above any plausible day's accumulation; it
# exists so a bug that stops rows disappearing cannot spin forever.
MAX_BATCHES = 10000


def run_purge_search_log(script: Script) -> None:
    before = datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)
    deleted = 0

    for batch in range(MAX_BATCHES):
        with script.context() as ctx:
            removed = delete_old_searches(ctx.db.get_app_db(), before, BATCH_SIZE)
            ctx.db.session.commit()
        if not removed:
            break
        deleted += removed
    else:
        logger.error(
            "Stopped after %d batches with rows still older than %s. Either the "
            "backlog is larger than this job can clear in one run, or deletes "
            "are not taking effect.",
            MAX_BATCHES,
            before.isoformat(),
        )

    if deleted:
        logger.info(
            "Deleted %d search log entries older than %s", deleted, before.isoformat()
        )
    else:
        logger.debug("No search log entries older than %s", before.isoformat())
