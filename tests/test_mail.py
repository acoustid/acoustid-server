import copy
import os
import socket
import uuid
from configparser import RawConfigParser
from typing import Any
from unittest import mock

import httpx
import pytest

import tests
from acoustid.config import MailConfig
from acoustid.mail import MailError, send_mail

MAILPIT_URL = os.environ.get("ACOUSTID_TEST_MAILPIT_URL", "http://127.0.0.1:8025")


def mail_config(**kwargs: Any) -> MailConfig:
    assert tests.script is not None
    config = copy.copy(tests.script.config.mail)
    for name, value in kwargs.items():
        setattr(config, name, value)
    return config


def unique_address() -> str:
    return "test-%s@example.com" % uuid.uuid4().hex


def find_messages(to: str) -> list[dict[str, Any]]:
    response = httpx.get(MAILPIT_URL + "/api/v1/search", params={"query": "to:" + to})
    response.raise_for_status()
    return response.json()["messages"]


def get_message(id: str) -> dict[str, Any]:
    response = httpx.get(MAILPIT_URL + "/api/v1/message/" + id)
    response.raise_for_status()
    return response.json()


def closed_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_send_mail_text_and_html() -> None:
    to = unique_address()
    send_mail(
        mail_config(),
        to,
        "Sign in to AcoustID",
        "Your code is 123456.\n",
        "<p>Your code is <b>123456</b>.</p>",
    )

    [summary] = find_messages(to)
    message = get_message(summary["ID"])
    assert message["From"] == {"Name": "AcoustID", "Address": "noreply@acoustid.test"}
    assert [r["Address"] for r in message["To"]] == [to]
    assert message["Subject"] == "Sign in to AcoustID"
    assert message["Text"].strip() == "Your code is 123456."
    assert "<b>123456</b>" in message["HTML"]
    assert message["MessageID"].endswith("@acoustid.test")
    assert message["Date"]


def test_send_mail_text_only() -> None:
    to = unique_address()
    send_mail(mail_config(), to, "Hello", "Just text.\n")

    [summary] = find_messages(to)
    message = get_message(summary["ID"])
    assert message["Text"].strip() == "Just text."
    assert message["HTML"] == ""


def test_send_mail_logs_in() -> None:
    to = unique_address()
    send_mail(mail_config(username="someone", password="secret"), to, "Hi", "Hi\n")

    [summary] = find_messages(to)
    assert summary["Username"] == "someone"


def test_send_mail_without_credentials_does_not_log_in() -> None:
    to = unique_address()
    send_mail(mail_config(username=None, password=None), to, "Hi", "Hi\n")

    [summary] = find_messages(to)
    assert summary["Username"] == ""


@pytest.mark.parametrize("field", ["host", "from_address"])
def test_send_mail_not_configured(field: str) -> None:
    with pytest.raises(MailError, match="not configured"):
        send_mail(mail_config(**{field: ""}), unique_address(), "Hi", "Hi\n")


def test_send_mail_connection_refused() -> None:
    with pytest.raises(MailError):
        send_mail(mail_config(port=closed_port()), unique_address(), "Hi", "Hi\n")


def test_send_mail_starttls_required() -> None:
    # Mailpit runs without a certificate, so it does not offer STARTTLS. The
    # message must not go out in plain text instead.
    to = unique_address()
    with pytest.raises(MailError):
        send_mail(mail_config(security="starttls"), to, "Hi", "Hi\n")
    assert find_messages(to) == []


def test_send_mail_tls_against_plain_server() -> None:
    to = unique_address()
    with pytest.raises(MailError):
        send_mail(mail_config(security="tls", timeout=2.0), to, "Hi", "Hi\n")
    assert find_messages(to) == []


@pytest.mark.parametrize("field", ["to", "subject"])
def test_send_mail_rejects_header_injection(field: str) -> None:
    to = unique_address()
    victim = unique_address()
    args = {"to": to, "subject": "Hi"}
    args[field] += "\r\nBcc: " + victim
    with pytest.raises(ValueError):
        send_mail(mail_config(), args["to"], args["subject"], "Hi\n")
    assert find_messages(to) == []
    assert find_messages(victim) == []


def test_mail_config_read_section() -> None:
    parser = RawConfigParser()
    parser.read_string(
        """
[mail]
host=smtp.example.com
port=465
security=tls
username=user
password=pass
from_address=AcoustID <noreply@example.com>
timeout=5
"""
    )
    config = MailConfig()
    config.read(parser, "mail")
    assert config.host == "smtp.example.com"
    assert config.port == 465
    assert config.security == "tls"
    assert config.username == "user"
    assert config.password == "pass"
    assert config.from_address == "AcoustID <noreply@example.com>"
    assert config.timeout == 5.0


def test_mail_config_defaults() -> None:
    config = MailConfig()
    config.read(RawConfigParser(), "mail")
    assert config.host == ""
    assert config.port == 587
    assert config.security == "starttls"
    assert config.username is None


def test_mail_config_read_env() -> None:
    env = {
        "X_MAIL_HOST": "smtp.example.com",
        "X_MAIL_PORT": "2525",
        "X_MAIL_SECURITY": "none",
        "X_MAIL_USERNAME": "user",
        "X_MAIL_PASSWORD": "pass",
        "X_MAIL_FROM_ADDRESS": "noreply@example.com",
        "X_MAIL_TIMEOUT": "3.5",
    }
    config = MailConfig()
    with mock.patch.dict(os.environ, env):
        config.read_env("X_")
    assert config.host == "smtp.example.com"
    assert config.port == 2525
    assert config.security == "none"
    assert config.username == "user"
    assert config.password == "pass"
    assert config.from_address == "noreply@example.com"
    assert config.timeout == 3.5


def test_mail_config_rejects_unknown_security() -> None:
    parser = RawConfigParser()
    parser.read_string("[mail]\nsecurity=ssl\n")
    with pytest.raises(ValueError, match="security"):
        MailConfig().read(parser, "mail")
    with mock.patch.dict(os.environ, {"X_MAIL_SECURITY": "ssl"}):
        with pytest.raises(ValueError, match="security"):
            MailConfig().read_env("X_")
