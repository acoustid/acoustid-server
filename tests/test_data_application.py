# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

from acoustid.data.application import (
    lookup_application_id_by_apikey,
    lookup_application_requires_user_key,
    update_application_status,
)
from tests import with_database


@with_database
def test_lookup_application_id_by_apikey(conn):
    id = lookup_application_id_by_apikey(conn, "app1key")
    assert 1 == id
    id = lookup_application_id_by_apikey(conn, "foooo")
    assert id is None


@with_database
def test_unknown_application_is_not_treated_as_exempt(conn) -> None:
    """Failing open here would hand out an exemption by accident.

    The flag says whether lookups need a user key, so a row that cannot be
    read must answer "yes, it does" -- otherwise a deleted or unreadable
    application becomes the one that gets to skip the policy.
    """
    assert lookup_application_requires_user_key(conn, 1) is True
    assert lookup_application_requires_user_key(conn, 123456) is True


@with_database
def test_application_exemption_round_trips(conn) -> None:
    update_application_status(conn, 1, True, requires_user_key=False)
    assert lookup_application_requires_user_key(conn, 1) is False
    update_application_status(conn, 1, True, requires_user_key=True)
    assert lookup_application_requires_user_key(conn, 1) is True


@with_database
def test_application_status_update_without_the_flag_preserves_it(
    conn,
) -> None:
    """acoustid.biz's hourly sync sends only `active`."""
    update_application_status(conn, 1, True, requires_user_key=False)
    update_application_status(conn, 1, False)
    assert lookup_application_requires_user_key(conn, 1) is False
