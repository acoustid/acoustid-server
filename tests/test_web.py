from nose.tools import assert_equal
from acoustid.web import db
from tests import make_web_application

app = None


def setup():
    global app
    app = make_web_application()
    app.config['TESTING'] = True


def test_track_page():
    client = app.test_client()

    rv = client.get('/track/eb31d1c3-950e-468b-9e36-e46fa75b1291')
    assert_equal(rv.status_code, 200)
    assert_equal(rv.data.count('Custom Track'), 1)
    assert_equal(rv.data.count('Custom Artist'), 1)
    assert not db.session.registry.has()
