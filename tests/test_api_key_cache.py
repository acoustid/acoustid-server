# Copyright (C) 2026 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

from typing import Any, Iterator

import cachetools
import pytest

from acoustid.api import v2

APPLICATION_ID = 111
ACCOUNT_ID = 222

SHARED_KEY = "the-same-string-in-both-roles"


class FakeDB(object):
    """Stands in for DatabaseContext; the lookups themselves are patched out."""

    def get_app_db(self, read_only: bool = False) -> object:
        return object()


@pytest.fixture(autouse=True)
def clear_api_key_caches() -> Iterator[None]:
    # The caches are module-level, so they outlive a single test. Found by type
    # rather than by name so that these tests assert on behaviour and stay
    # runnable against any arrangement of the caches.
    caches = [v for v in vars(v2).values() if isinstance(v, cachetools.Cache)]

    def clear() -> None:
        for cache in caches:
            cache.clear()

    clear()
    yield
    clear()


@pytest.fixture
def patched_lookups(monkeypatch: pytest.MonkeyPatch) -> None:
    def lookup_application_id_by_apikey(db: Any, apikey: str, **kwargs: Any) -> int:
        return APPLICATION_ID

    def lookup_account_id_by_apikey(db: Any, apikey: str) -> int:
        return ACCOUNT_ID

    monkeypatch.setattr(
        v2, "lookup_application_id_by_apikey", lookup_application_id_by_apikey
    )
    monkeypatch.setattr(v2, "lookup_account_id_by_apikey", lookup_account_id_by_apikey)


def test_user_lookup_does_not_return_an_application_id(
    patched_lookups: None,
) -> None:
    """A submit parses client before user, so the app key is cached first.

    Sharing one cache keyed on the bare API key, the second call hit the first
    one's entry and the account id came back as an application id.
    """
    db = FakeDB()

    assert v2.check_app_api_key(None, db, SHARED_KEY) == APPLICATION_ID
    assert v2.check_user_api_key(None, db, SHARED_KEY) == ACCOUNT_ID


def test_application_lookup_does_not_return_an_account_id(
    patched_lookups: None,
) -> None:
    """The other order, which is reachable across requests within the TTL.

    An account API key sent as `client=` returns that account's id as an
    application id -- the shape seen in the poisoned stats counters.
    """
    db = FakeDB()

    assert v2.check_user_api_key(None, db, SHARED_KEY) == ACCOUNT_ID
    assert v2.check_app_api_key(None, db, SHARED_KEY) == APPLICATION_ID


def test_each_lookup_is_still_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    """Namespacing the keys must not stop either lookup being cached."""
    calls = {"app": 0, "user": 0}

    def lookup_application_id_by_apikey(db: Any, apikey: str, **kwargs: Any) -> int:
        calls["app"] += 1
        return APPLICATION_ID

    def lookup_account_id_by_apikey(db: Any, apikey: str) -> int:
        calls["user"] += 1
        return ACCOUNT_ID

    monkeypatch.setattr(
        v2, "lookup_application_id_by_apikey", lookup_application_id_by_apikey
    )
    monkeypatch.setattr(v2, "lookup_account_id_by_apikey", lookup_account_id_by_apikey)

    db = FakeDB()
    for _ in range(3):
        assert v2.check_app_api_key(None, db, SHARED_KEY) == APPLICATION_ID
        assert v2.check_user_api_key(None, db, SHARED_KEY) == ACCOUNT_ID

    assert calls == {"app": 1, "user": 1}
