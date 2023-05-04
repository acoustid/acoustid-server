# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

from nose.tools import assert_equals, assert_raises, assert_true, assert_false
from acoustid.utils import singular, is_uuid, is_foreignid, generate_demo_client_api_key


def test_singular():
    # type: () -> None
    assert_equals('artist', singular('artists'))
    assert_equals('release', singular('releases'))
    assert_equals('city', singular('cities'))
    assert_raises(ValueError, singular, 'city')


def test_is_uuid():
    # type: () -> None
    assert_true(is_uuid('83fdc319-b05e-4edc-9371-f7ff09fc642e'))
    assert_false(is_uuid('83fdc319-b05e-4edc-9371-xxxxxxxxxxxx'))


def test_is_foreignid():
    # type: () -> None
    assert_true(is_foreignid('abc:123'))
    assert_true(is_foreignid('foo:123'))
    assert_false(is_foreignid('ABC:83'))
    assert_false(is_foreignid('83'))


def test_generate_demo_client_api_key() -> None:
    token = generate_demo_client_api_key('foo')
    assert token != ''
