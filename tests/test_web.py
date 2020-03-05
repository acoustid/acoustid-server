from nose.tools import assert_equal
from acoustid.web import db
from tests import make_web_application

app = None


def setup():
    # type: () -> None
    global app
    app = make_web_application()
    app.config['TESTING'] = True


def test_track_page():
    # type: () -> None
    assert app is not None
    client = app.test_client()

    rv = client.get('/track/eb31d1c3-950e-468b-9e36-e46fa75b1291')
    assert_equal(rv.status_code, 200)
    assert_equal(rv.data.count(b'Custom Track'), 2)
    assert_equal(rv.data.count(b'Custom Artist'), 2)
    assert not db.session.registry.has()
