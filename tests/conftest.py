import os
from unittest import mock

import pytest

import tests


@pytest.fixture(scope="session")
def config_file() -> str:
    return os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "acoustid-test.conf"
    )


@pytest.fixture(scope="session", autouse=True)
def setup(config_file: str):
    with mock.patch("acoustid.data.fingerprint.SEARCH_ONLY_IN_DATABASE", True):
        tests.setup(config_file)
        yield
        tests.teardown()
