# Copyright (C) 2026 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

from typing import Any
from unittest import mock

import pytest
from sqlalchemy.exc import IntegrityError

from acoustid.script import Script
from acoustid.scripts import update_lookup_stats as script_module
from acoustid.scripts.update_lookup_stats import run_update_lookup_stats

from . import with_script

ROOT_KEY = "lookups:00"

KNOWN_APPLICATION_ID = 1
UNKNOWN_APPLICATION_ID = 215940


class UnknownApplication(Exception):
    """Stands in for psycopg2.errors.ForeignKeyViolation."""

    pgcode = "23503"


def foreign_key_violation() -> IntegrityError:
    return IntegrityError("INSERT INTO stats_lookups ...", {}, UnknownApplication())


@with_script
def test_discards_counter_for_unknown_application(script: Script) -> None:
    """A counter naming a missing application must not wedge the partition.

    The insert violates the foreign key however often it is retried. The error
    used to escape the loop, so the key stayed in redis and every counter
    behind it was never applied either.
    """
    applied: list[int] = []

    def fake_update(db: Any, application_id: int, *args: Any, **kwargs: Any) -> None:
        if application_id == UNKNOWN_APPLICATION_ID:
            raise foreign_key_violation()
        applied.append(application_id)

    redis = script.get_redis()
    redis.delete(ROOT_KEY)
    poisoned = f"2026-07-28:10:{UNKNOWN_APPLICATION_ID}:hit"
    good = f"2026-07-28:10:{KNOWN_APPLICATION_ID}:hit"
    redis.hset(ROOT_KEY, poisoned, 5)
    redis.hset(ROOT_KEY, good, 7)

    with mock.patch.object(script_module, "update_lookup_stats", fake_update):
        run_update_lookup_stats(script, 0)

    # The counter behind the poisoned one was still applied.
    assert applied == [KNOWN_APPLICATION_ID]
    # The poisoned key is gone, so the next run does not trip over it again.
    assert redis.hget(ROOT_KEY, poisoned) is None
    # The good one was decremented rather than deleted.
    remaining = redis.hget(ROOT_KEY, good)
    assert remaining is not None
    assert int(remaining) == 0

    redis.delete(ROOT_KEY)


@with_script
def test_other_integrity_errors_still_propagate(script: Script) -> None:
    """Only a missing application is discarded; anything else must surface."""

    class SomethingElse(Exception):
        pgcode = "23505"  # unique_violation

    def fake_update(db: Any, application_id: int, *args: Any, **kwargs: Any) -> None:
        raise IntegrityError("INSERT INTO stats_lookups ...", {}, SomethingElse())

    redis = script.get_redis()
    redis.delete(ROOT_KEY)
    key = f"2026-07-28:10:{KNOWN_APPLICATION_ID}:hit"
    redis.hset(ROOT_KEY, key, 1)

    with mock.patch.object(script_module, "update_lookup_stats", fake_update):
        with pytest.raises(IntegrityError):
            run_update_lookup_stats(script, 0)

    # Not discarded, so it is retried rather than silently dropped.
    remaining = redis.hget(ROOT_KEY, key)
    assert remaining is not None
    assert int(remaining) == 1

    redis.delete(ROOT_KEY)
