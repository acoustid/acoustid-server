import pytest
from flask import Flask

from acoustid.web import db
from tests import make_web_application


@pytest.fixture()
def app() -> Flask:
    app = make_web_application()
    app.config["TESTING"] = True
    return app


def test_home_page(app: Flask) -> None:
    client = app.test_client()

    rv = client.get("/")
    assert rv.status_code == 200
    assert "Welcome to AcoustID" in rv.text


def test_docs_page(app: Flask) -> None:
    client = app.test_client()

    rv = client.get("/docs")
    assert rv.status_code == 200
    assert "Documentation" in rv.text


def test_chromaprint_page(app: Flask) -> None:
    client = app.test_client()

    rv = client.get("/chromaprint")
    assert rv.status_code == 200


def test_faq_page(app: Flask) -> None:
    client = app.test_client()

    rv = client.get("/faq")
    assert rv.status_code == 200


def test_webservice_page(app: Flask) -> None:
    client = app.test_client()

    rv = client.get("/webservice")
    assert rv.status_code == 200
    assert "/v2/lookup" in rv.text
    assert "/v2/submit" in rv.text


def test_stats_page(app: Flask) -> None:
    client = app.test_client()

    rv = client.get("/stats")
    assert rv.status_code == 200
    assert "Basic statistics" in rv.text
    assert "Daily additions" in rv.text


def test_login_page(app: Flask) -> None:
    client = app.test_client()

    rv = client.get("/login")
    assert rv.status_code == 200


def test_contact_page(app: Flask) -> None:
    client = app.test_client()

    rv = client.get("/contact")
    assert rv.status_code == 200
    assert "info@acoustid.org" in rv.text


def test_track_page(app: Flask) -> None:
    client = app.test_client()

    rv = client.get("/track/eb31d1c3-950e-468b-9e36-e46fa75b1291")
    assert rv.status_code == 200
    assert "b81f83ee-4da4-11e0-9ed8-0025225356f3" in rv.text
    assert rv.data.count(b"Custom Track") == 2
    assert rv.data.count(b"Custom Artist") == 2
    assert not db.session.registry.has()


def test_track_page_show_disabled(app: Flask) -> None:
    client = app.test_client()

    rv = client.get("/track/eb31d1c3-950e-468b-9e36-e46fa75b1291")
    assert "54b7b412-fc69-4fc7-8c96-17800eda3a98" not in rv.text
    assert "Show 1 disabled recording" in rv.text
    assert rv.status_code == 200

    rv = client.get("/track/eb31d1c3-950e-468b-9e36-e46fa75b1291?disabled=1")
    assert "54b7b412-fc69-4fc7-8c96-17800eda3a98" in rv.text
    assert "Show 1 disabled recording" not in rv.text
    assert rv.status_code == 200
