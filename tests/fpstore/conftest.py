import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from acoustid.future.fpstore.app import create_app


@pytest.fixture
def app() -> Starlette:
    return create_app()


@pytest.fixture
def client(app: Starlette) -> TestClient:
    return TestClient(app)
