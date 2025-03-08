import os

import pytest

import tests


@pytest.fixture(scope="session")
def config_file() -> str:
    return os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "acoustid-test.conf"
    )


@pytest.fixture(scope="session", autouse=True)
def setup(config_file: str):
    tests.setup(config_file)
    yield
    tests.teardown()
