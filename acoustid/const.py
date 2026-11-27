# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import datetime

# minimum similarity with the best matching fingerprint
TRACK_MERGE_THRESHOLD = 0.75

# minimum similarity with the worst matching fingerprint
TRACK_GROUP_MERGE_THRESHOLD = 0.4

# maximum alignment differences of fingerprints in a track
TRACK_MAX_OFFSET = 80

# minimum similarity for two fingerprints to be considered the same
FINGERPRINT_MERGE_THRESHOLD = 0.9

# how many items must a fingerprint have to be indexed
FINGERPRINT_MIN_UNIQUE_ITEMS = 80

FINGERPRINT_MAX_LENGTH_DIFF = 7

FINGERPRINT_MAX_ALLOWED_LENGTH_DIFF = 30

MAX_REQUESTS_PER_SECOND = 4

DEFAULT_GLOBAL_RATE_LIMIT = 100

# how many past days the public data export looks at in one run
EXPORT_MAX_DAYS = 30

# Lookups must carry a user API key in the `user` parameter from this date.
# Until then a missing or empty `user` is accepted, so clients have a window
# to add one; an invalid key is rejected either way, because sending a key
# that does not work is a bug the caller wants to hear about now rather than
# in 2027. Announced at
# https://blog.acoustid.org/posts/2026-11-19-user-api-keys-required-for-lookups/
LOOKUP_USER_REQUIRED_FROM = datetime.date(2027, 1, 1)

# How long a link code from the user key link flow stays usable.
USER_KEY_LINK_TTL = datetime.timedelta(minutes=15)

# Limits on starting the link flow. Application keys are public, so the
# per-application cap is only a backstop: hitting it blocks that application's
# users from linking, which is what the per-IP limit is there to prevent.
USER_KEY_LINK_REQUESTS_PER_IP_PER_HOUR = 10
USER_KEY_MAX_PENDING_LINKS_PER_APPLICATION = 10000

# An approved key stops working this long after it was last used, so keys
# for machines that no longer exist lapse while working ones never do.
USER_KEY_LIFETIME_DAYS = 365
# Link requests nobody approved are kept this long after their code expired,
# so link_status can still say "declined" or "expired", then deleted.
ABANDONED_LINK_REQUEST_RETENTION = datetime.timedelta(days=30)
# Per-user daily lookup counts are kept this long, for spotting outliers.
USER_LOOKUP_STATS_RETENTION = datetime.timedelta(days=30)
# Per-IP user agent counts are personal data; the privacy policy promises
# they are deleted after this long.
USER_AGENT_STATS_RETENTION = datetime.timedelta(days=90)
