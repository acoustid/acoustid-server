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
