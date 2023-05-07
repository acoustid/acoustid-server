import pytest

import tests


@pytest.fixture(scope="session", autouse=True)
def setup():
    tests.setup()
    yield
    tests.teardown()
