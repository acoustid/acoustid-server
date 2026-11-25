import copy
import os
import smtplib
import socket
import ssl
import uuid
from configparser import RawConfigParser
from typing import Any
from unittest import mock

import httpx
import pytest

import tests
from acoustid.config import Config, MailConfig
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
    with pytest.raises(MailError) as exc_info:
        send_mail(mail_config(security="starttls"), to, "Hi", "Hi\n")
    assert isinstance(exc_info.value.__cause__, smtplib.SMTPNotSupportedError)
    assert find_messages(to) == []


def test_send_mail_tls_against_plain_server() -> None:
    to = unique_address()
    with pytest.raises(MailError) as exc_info:
        send_mail(mail_config(security="tls", timeout=2.0), to, "Hi", "Hi\n")
    assert isinstance(exc_info.value.__cause__, ssl.SSLError)
    assert find_messages(to) == []


def assert_verifying(context: Any) -> None:
    assert isinstance(context, ssl.SSLContext)
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname


def test_send_mail_tls_verifies_certificate() -> None:
    with mock.patch("smtplib.SMTP_SSL") as smtp_ssl:
        send_mail(mail_config(security="tls"), unique_address(), "Hi", "Hi\n")
    assert_verifying(smtp_ssl.call_args.kwargs["context"])


def test_send_mail_starttls_verifies_certificate() -> None:
    with mock.patch("smtplib.SMTP") as smtp:
        send_mail(mail_config(security="starttls"), unique_address(), "Hi", "Hi\n")
    assert_verifying(smtp.return_value.starttls.call_args.kwargs["context"])


def test_send_mail_ignores_quit_failure() -> None:
    to = unique_address()
    with mock.patch(
        "smtplib.SMTP.quit", side_effect=smtplib.SMTPServerDisconnected("gone")
    ):
        send_mail(mail_config(), to, "Hi", "Hi\n")
    assert len(find_messages(to)) == 1


def test_send_mail_no_quit_after_failed_send() -> None:
    with (
        mock.patch(
            "smtplib.SMTP.send_message",
            side_effect=smtplib.SMTPDataError(451, b"later"),
        ),
        mock.patch("smtplib.SMTP.quit") as quit,
    ):
        with pytest.raises(MailError) as exc_info:
            send_mail(mail_config(), unique_address(), "Hi", "Hi\n")
    assert isinstance(exc_info.value.__cause__, smtplib.SMTPDataError)
    quit.assert_not_called()


def test_send_mail_non_ascii_credentials() -> None:
    with pytest.raises(MailError):
        send_mail(
            mail_config(username="\u00fc", password="x"), unique_address(), "Hi", "Hi\n"
        )


def test_send_mail_does_not_log_recipient(caplog: pytest.LogCaptureFixture) -> None:
    to = unique_address()
    refused = smtplib.SMTPRecipientsRefused({to: (550, b"no such user")})
    with mock.patch("smtplib.SMTP.send_message", side_effect=refused):
        with pytest.raises(MailError) as exc_info:
            send_mail(mail_config(), to, "Hi", "Hi\n")
    assert to not in str(exc_info.value)
    assert "SMTPRecipientsRefused" in caplog.text
    assert to not in caplog.text


@pytest.mark.parametrize(
    "to",
    [
        "{a}, {b}",
        "{a},{b}",
        "{a}; {b}",
        "Someone <{b}>",
        "<{b}>",
        " {a}",
        "{a} ",
        "a@b@example.com",
        "not-an-address",
        "@example.com",
        "user@",
        "{a}\r\nBcc: {b}",
        "{a}\n",
        "{a}\x85",
        "{a}\u2028",
        "user\x00{a}",
        "=?utf-8?q?x?={a}",
        "",
    ],
)
def test_send_mail_rejects_anything_but_one_address(to: str) -> None:
    a = unique_address()
    b = unique_address()
    with pytest.raises(ValueError):
        send_mail(mail_config(), to.format(a=a, b=b), "Hi", "Hi\n")
    assert find_messages(a) == []
    assert find_messages(b) == []


@pytest.mark.parametrize(
    "subject", ["Hi\r\nBcc: {victim}", "Hi\nBcc: {victim}", "Hi\n", "Hi\r\n", "Hi\r"]
)
def test_send_mail_rejects_line_breaks_in_subject(subject: str) -> None:
    to = unique_address()
    victim = unique_address()
    with pytest.raises(ValueError):
        send_mail(mail_config(), to, subject.format(victim=victim), "Hi\n")
    assert find_messages(to) == []
    assert find_messages(victim) == []


def test_send_mail_rejects_line_breaks_in_from_address() -> None:
    to = unique_address()
    config = mail_config(from_address="AcoustID <noreply@acoustid.test>\n")
    with pytest.raises(ValueError):
        send_mail(config, to, "Hi", "Hi\n")
    assert find_messages(to) == []


def test_send_mail_multiline_bodies() -> None:
    to = unique_address()
    send_mail(mail_config(), to, "Hi", "one\r\ntwo\n", "<p>one</p>\n<p>two</p>\n")
    [summary] = find_messages(to)
    message = get_message(summary["ID"])
    assert message["Text"].splitlines() == ["one", "two"]
    assert "<p>two</p>" in message["HTML"]


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


def load_config(tmp_path: Any, text: str, env: dict[str, str] = {}) -> Config:
    path = tmp_path / "acoustid.conf"
    path.write_text(text)
    config = Config()
    config.read(str(path))
    with mock.patch.dict(os.environ, env):
        config.read_env()
    return config


@pytest.mark.parametrize(
    "option", ["port=0", "port=65536", "timeout=0", "timeout=-1", "timeout=inf"]
)
def test_mail_config_rejects_bad_numbers(tmp_path: Any, option: str) -> None:
    with pytest.raises(ValueError):
        load_config(tmp_path, "[mail]\n" + option + "\n")


def test_mail_config_warns_about_plain_text_credentials(
    tmp_path: Any, caplog: pytest.LogCaptureFixture
) -> None:
    load_config(tmp_path, "[mail]\nsecurity=none\nusername=user\n")
    assert caplog.text.count("unencrypted") == 1


def test_mail_config_rejects_unknown_security(tmp_path: Any) -> None:
    with pytest.raises(ValueError, match="security"):
        load_config(tmp_path, "[mail]\nsecurity=ssl\n")
    with pytest.raises(ValueError, match="security"):
        load_config(tmp_path, "", {"ACOUSTID_MAIL_SECURITY": "ssl"})


def test_mail_config_env_overrides_bad_file_value(tmp_path: Any) -> None:
    config = load_config(
        tmp_path, "[mail]\nsecurity=ssl\n", {"ACOUSTID_MAIL_SECURITY": "tls"}
    )
    assert config.mail.security == "tls"
