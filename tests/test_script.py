# Copyright (C) 2026 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import contextlib
from typing import Iterator, List
from unittest import mock

import sentry_sdk
from sentry_sdk.envelope import Envelope
from sentry_sdk.sessions import track_session
from sentry_sdk.transport import Transport

from acoustid.script import Script


def init_kwargs(config_file: str) -> dict:
    with mock.patch.object(sentry_sdk, "init") as init:
        with mock.patch.object(sentry_sdk, "set_tag"):
            Script(config_file).setup_sentry(component="tests")
    assert init.call_count == 1
    return init.call_args.kwargs


def test_sentry_session_tracking_is_off(config_file: str) -> None:
    """Sessions are dropped by the backend, and they were the only traffic in
    its request log, which hid whether real errors were arriving."""
    assert init_kwargs(config_file)["auto_session_tracking"] is False


def test_sentry_error_delivery_is_left_alone(config_file: str) -> None:
    """Turning sessions off must not quietly turn errors down with them."""
    kwargs = init_kwargs(config_file)
    assert "sample_rate" not in kwargs
    assert "before_send" not in kwargs
    assert kwargs["send_default_pii"] is True


class RecordingTransport(Transport):
    """Records the envelope item types the SDK puts on the wire."""

    def __init__(self) -> None:
        self.items: List[str] = []

    def capture_envelope(self, envelope: Envelope) -> None:
        self.items.extend(item.type for item in envelope.items if item.type)

    def flush(self, timeout: float, callback: object = None) -> None:
        pass

    def kill(self) -> None:
        pass


@contextlib.contextmanager
def recording_sentry(*, auto_session_tracking: bool) -> Iterator[RecordingTransport]:
    """A real initialised SDK, put back the way it was afterwards."""
    transport = RecordingTransport()
    previous = sentry_sdk.get_global_scope().client
    try:
        sentry_sdk.init(
            dsn="https://key@sentry.invalid/1",
            transport=transport,
            auto_session_tracking=auto_session_tracking,
        )
        yield transport
    finally:
        sentry_sdk.get_global_scope().set_client(previous)


def capture_one_error(*, auto_session_tracking: bool) -> List[str]:
    """Send one error through the per-request path the WSGI integration uses."""
    with recording_sentry(auto_session_tracking=auto_session_tracking) as transport:
        scope = sentry_sdk.get_isolation_scope()
        with track_session(scope, session_mode="request"):
            try:
                raise RuntimeError("an error worth reporting")
            except RuntimeError:
                sentry_sdk.capture_exception()
        sentry_sdk.flush()
        return sorted(set(transport.items))


def test_no_sessions_envelope_is_produced() -> None:
    """The behaviour, not just the keyword: the item the backend discards
    stops being sent, and the error event still is."""
    assert capture_one_error(auto_session_tracking=False) == ["event"]


def test_the_sessions_envelope_is_what_we_turned_off() -> None:
    """The other half of the pair. Without it the test above would pass just as
    well against an SDK that had stopped sending sessions on its own, and would
    stop telling us anything about our own configuration."""
    assert capture_one_error(auto_session_tracking=True) == ["event", "sessions"]
