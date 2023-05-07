# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import pytest

from acoustid.utils import generate_demo_client_api_key, is_foreignid, is_uuid, singular


def test_singular() -> None:
    assert "artist" == singular("artists")
    assert "release" == singular("releases")
    assert "city" == singular("cities")
    with pytest.raises(ValueError):
        singular("city")


def test_is_uuid() -> None:
    assert is_uuid("83fdc319-b05e-4edc-9371-f7ff09fc642e") is True
    assert is_uuid("83fdc319-b05e-4edc-9371-xxxxxxxxxxxx") is False


def test_is_foreignid() -> None:
    assert is_foreignid("abc:123") is True
    assert is_foreignid("foo:123") is True
    assert is_foreignid("ABC:83") is False
    assert is_foreignid("83") is False


def test_generate_demo_client_api_key() -> None:
    token = generate_demo_client_api_key("foo")
    assert token != ""
