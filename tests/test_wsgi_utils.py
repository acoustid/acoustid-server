# Copyright (C) 2026 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

from typing import Any

import pytest

from acoustid import wsgi_utils
from acoustid.config import Config


def capture(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """Run one of the app launchers without exec'ing gunicorn."""
    calls: list[list[str]] = []

    def fake_run(config: Any, args: list[str]) -> int:
        calls.append(args)
        return 0

    monkeypatch.setattr(wsgi_utils, "run_gunicorn", fake_run)
    return calls


def worker_class(args: list[str]) -> str | None:
    return args[args.index("--worker-class") + 1] if "--worker-class" in args else None


@pytest.mark.parametrize(
    "launch,entrypoint",
    [
        (wsgi_utils.run_api_app, "acoustid.wsgi_api_app:application"),
        (wsgi_utils.run_web_app, "acoustid.wsgi_web_app:application"),
    ],
)
def test_gevent_apps_load_the_patched_entrypoint(
    monkeypatch: pytest.MonkeyPatch, launch: Any, entrypoint: str
) -> None:
    """A gevent worker must not be pointed at an unpatched application.

    gevent cannot see into psycopg2, so without psycogreen every query blocks
    the whole worker rather than one greenlet -- concurrent requests stall
    behind each other and it shows up as latency, not as an error. The
    patching lives in the wsgi_*_app modules and has to happen before the app
    is imported, so the worker class and the entrypoint have to change
    together or not at all.
    """
    calls = capture(monkeypatch)
    launch(Config())

    args = calls[0]
    assert worker_class(args) == "gevent"
    assert args[-1] == entrypoint or entrypoint in args


def test_the_two_apps_bind_different_ports(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = capture(monkeypatch)
    wsgi_utils.run_api_app(Config())
    wsgi_utils.run_web_app(Config())

    bindings = [args[args.index("--bind") + 1] for args in calls]
    assert bindings == ["0.0.0.0:3031", "0.0.0.0:3032"]
