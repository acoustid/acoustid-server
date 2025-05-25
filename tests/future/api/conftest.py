import os
from typing import Iterator

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from acoustid.future.api.app import create_app


@pytest.fixture
def app(config_file: str) -> Starlette:
    return create_app(config_file, tests=True)


@pytest.fixture
def client(app: Starlette) -> Iterator[TestClient]:
    with TestClient(app) as client:
        yield client
