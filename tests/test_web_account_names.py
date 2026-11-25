# Copyright (C) 2026 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import os
import re
from types import SimpleNamespace
from typing import Any, Iterator

import pytest
from flask import Flask, render_template_string

from acoustid import tables as schema
from tests import make_web_application

TEMPLATES = os.path.join(
    os.path.dirname(__file__), "..", "acoustid", "web", "templates"
)


@pytest.fixture()
def app(config_file: str) -> Iterator[Flask]:
    app = make_web_application(config_file)
    app.config["TESTING"] = True
    yield app
    with app.acoustid_script.context() as ctx:  # type: ignore
        ctx.db.get_app_db().execute(schema.account.update().values(mbuser=None))
        ctx.db.session.commit()


def render(app: Flask, account: Any) -> str:
    with app.test_request_context():
        return render_template_string(
            '{% from "_macros.html" import account_name %}{{ account_name(a) }}',
            a=account,
        )


def test_musicbrainz_account(app: Flask) -> None:
    html = render(app, SimpleNamespace(id=7, mbuser="Some User", name="ignored"))
    assert 'href="https://musicbrainz.org/user/Some%20User"' in html
    assert 'class="mb-icon"' in html
    assert 'aria-label="MusicBrainz"' in html
    assert ">Some User</a>" in html
    assert "ignored" not in html
    assert "user7" not in html


def test_musicbrainz_name_with_a_slash(app: Flask) -> None:
    # Links to that user's profile, not to a subpage of another user's.
    html = render(app, SimpleNamespace(id=1, mbuser="foo/ratings", name=""))
    assert 'href="https://musicbrainz.org/user/foo%2Fratings"' in html


def test_other_account(app: Flask) -> None:
    html = render(app, SimpleNamespace(id=7, mbuser=None, name="Google Account"))
    assert html == '<span class="account-name muted">user7</span>'


def test_deleted_account(app: Flask) -> None:
    assert "(deleted account)" in render(app, None)


def test_musicbrainz_user_named_like_an_id(app: Flask) -> None:
    # Someone can register "user1234" at MusicBrainz; it must still look
    # different from account 1234.
    mb = render(app, SimpleNamespace(id=1, mbuser="user1234", name=""))
    plain = render(app, SimpleNamespace(id=1234, mbuser=None, name=""))
    assert mb != plain
    assert "mb-icon" in mb and "<a " in mb
    assert "mb-icon" not in plain and "<a " not in plain


def test_musicbrainz_name_is_escaped(app: Flask) -> None:
    html = render(app, SimpleNamespace(id=1, mbuser='<b>x</b>"', name=""))
    assert "<b>x</b>" not in html
    assert "&lt;b&gt;x&lt;/b&gt;" in html


def test_account_page(app: Flask) -> None:
    client = app.test_client()
    with client.session_transaction() as flask_session:
        flask_session["id"] = 2
    page = client.get("/api-key").data.decode()
    assert 'Signed in as <span class="account-name muted">user2</span>' in page
    assert "User 2" not in page

    with app.acoustid_script.context() as ctx:  # type: ignore
        ctx.db.get_app_db().execute(
            schema.account.update()
            .where(schema.account.c.id == 2)
            .values(mbuser="mbtwo")
        )
        ctx.db.session.commit()
    page = client.get("/api-key").data.decode()
    assert 'href="https://musicbrainz.org/user/mbtwo"' in page


def test_templates_show_accounts_only_through_the_macro() -> None:
    # The rule lives in one place: no template prints a stored account name.
    pattern = re.compile(r"(user|account)\.(name|mbuser)\b")
    offenders = []
    names = []
    for root, _, files in os.walk(TEMPLATES):
        for file in files:
            names.append(os.path.relpath(os.path.join(root, file), TEMPLATES))
    assert "mail/signin.txt" in names
    for name in sorted(names):
        if name == "_macros.html":
            continue
        with open(os.path.join(TEMPLATES, name)) as f:
            for number, line in enumerate(f, 1):
                if pattern.search(line):
                    offenders.append("%s:%d: %s" % (name, number, line.strip()))
    assert offenders == []
