# Copyright (C) 2026 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

from unittest import mock

import pytest
from werkzeug.datastructures import MultiDict

from acoustid.utils import normalize_format_name
from tests import with_script_context

# Taken from production, where about a quarter of the format table turned out
# to be filenames and track titles rather than codec names.
KEPT = [
    "FLAC",
    "MP3",
    "PCM_S16LE",
    "M4B",
    "Ogg Vorbis",
    "Monkey's Audio",
]

DROPPED = [
    ". Skrillex - Snake Eyes - 02 - Torture Me.mp3",
    ". Skrillex - Boiler Room: 100 gecs in Los Angeles, Mar 5, 2023 "
    "(DJ Mix) - 32 - Torture Me.m4a",
    "(Feat. Conquer Divide)/10 Years",
    "a.mp3",
    "C:\\Music\\track.flac",
    "/home/user/music/track.flac",
    "x" * 33,
    "",
    "   ",
]


@pytest.mark.parametrize("name", KEPT)
def test_real_format_names_are_kept(name: str) -> None:
    assert normalize_format_name(name) == name


@pytest.mark.parametrize("name", DROPPED)
def test_values_that_are_not_formats_are_dropped(name: str) -> None:
    assert normalize_format_name(name) is None


def test_none_stays_none() -> None:
    assert normalize_format_name(None) is None


def test_surrounding_space_is_trimmed() -> None:
    assert normalize_format_name("  FLAC  ") == "FLAC"


def test_the_length_cap_is_the_boundary() -> None:
    assert normalize_format_name("x" * 32) == "x" * 32
    assert normalize_format_name("x" * 33) is None


# The boundary. Both API versions fill p["format"] in their own
# _parse_duration_and_format, so the normalisation lives in the shared
# _parse_submission.


@with_script_context
def test_the_parsed_submission_format_is_normalised(ctx) -> None:
    from acoustid.api.v2 import SubmitHandlerParams

    def parsed(value):
        params = SubmitHandlerParams(ctx.config)
        params.submissions = []
        values = MultiDict({"duration": "120", "fileformat": value, "fingerprint": "x"})
        with mock.patch("acoustid.api.v2.decode_fingerprint", return_value=[1, 2, 3]):
            params._parse_submission(values, "")
        return params.submissions[0]["format"]

    assert parsed("FLAC") == "FLAC"
    assert parsed("a.mp3") is None
    assert parsed(". Skrillex - Snake Eyes - 02 - Torture Me.mp3") is None


def test_v1_inherits_the_normalising_parse() -> None:
    """v1 overrides _parse_duration_and_format but not _parse_submission, which
    is why the normalisation sits in the latter. If that ever changes, v1 stops
    being covered and this says so."""
    from acoustid.api import v1, v2

    assert (
        v1.SubmitHandlerParams._parse_submission
        is v2.SubmitHandlerParams._parse_submission
    )
