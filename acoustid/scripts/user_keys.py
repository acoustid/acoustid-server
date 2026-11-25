# Copyright (C) 2026 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import logging

from acoustid.data.account import delete_abandoned_link_requests
from acoustid.data.email import delete_expired_email_confirmations
from acoustid.data.stats import delete_old_user_lookup_stats
from acoustid.script import Script

logger = logging.getLogger(__name__)


def run_cleanup_user_keys(script: Script) -> None:
    with script.context() as ctx:
        db = ctx.db.get_app_db()
        requests = delete_abandoned_link_requests(db)
        stats = delete_old_user_lookup_stats(db)
        confirmations = delete_expired_email_confirmations(db)
        ctx.db.session.commit()
        logger.info(
            "Deleted %d abandoned link requests, %d old user stats rows "
            "and %d expired email confirmations",
            requests,
            stats,
            confirmations,
        )
