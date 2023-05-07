import pytest
from flask import Flask

from acoustid.web import db
from tests import make_web_application


@pytest.fixture()
def app() -> Flask:
    app = make_web_application()
    app.config['TESTING'] = True
    return app


def test_home_page(app: Flask) -> None:
    client = app.test_client()

    rv = client.get('/')
    assert rv.status_code == 200
    assert 'Welcome to AcoustID' in rv.text


def test_docs_page(app: Flask) -> None:
    client = app.test_client()

    rv = client.get('/docs')
    assert rv.status_code == 200
    assert 'Documentation' in rv.text


def test_chromaprint_page(app: Flask) -> None:
    client = app.test_client()

    rv = client.get('/chromaprint')
    assert rv.status_code == 200


def test_faq_page(app: Flask) -> None:
    client = app.test_client()

    rv = client.get('/faq')
    assert rv.status_code == 200


def test_webservice_page(app: Flask) -> None:
    client = app.test_client()

    rv = client.get('/webservice')
    assert rv.status_code == 200
    assert '/v2/lookup' in rv.text
    assert '/v2/submit' in rv.text


def test_stats_page(app: Flask) -> None:
    client = app.test_client()

    rv = client.get('/stats')
    assert rv.status_code == 200
    assert 'Basic statistics' in rv.text
    assert 'Daily additions' in rv.text


def test_login_page(app: Flask) -> None:
    client = app.test_client()

    rv = client.get('/login')
    assert rv.status_code == 200


def test_contact_page(app: Flask) -> None:
    client = app.test_client()

    rv = client.get('/login')
    assert rv.status_code == 200
    assert 'info@acoustid.org' in rv.text


def test_track_page(app: Flask) -> None:
    client = app.test_client()

    rv = client.get('/track/eb31d1c3-950e-468b-9e36-e46fa75b1291')
    assert rv.status_code == 200
    assert rv.data.count(b'Custom Track') == 2
    assert rv.data.count(b'Custom Artist') == 2
    assert not db.session.registry.has()
