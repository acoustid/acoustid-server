# Copyright (C) 2026 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

"""Outgoing mail over SMTP.

Plain SMTP keeps the code independent of the provider: switching is a config
change. Mail is sent synchronously. The timeout in the config applies to each
connect and each read or write on the socket, not to the whole exchange, which
takes about ten round trips.
"""

import logging
import smtplib
import ssl
from email.message import EmailMessage
from email.policy import SMTP
from email.utils import formatdate, make_msgid, parseaddr

from acoustid.config import MailConfig

logger = logging.getLogger(__name__)


class MailError(Exception):
    """The message could not be handed to the SMTP server."""


def check_recipient(to: str) -> None:
    # The envelope recipients would otherwise be parsed out of the To header,
    # so "victim@example.com, attacker@example.com" would mail both.
    name, addr = parseaddr(to)
    local, _, domain = addr.partition("@")
    if (
        name
        or addr != to
        or not local
        or not domain
        or "@" in domain
        or not addr.isprintable()
        or any(c in addr for c in ',;<>"\\ ')
        or "=?" in addr
    ):
        raise ValueError("expected a single bare email address")


def describe_error(e: Exception) -> str:
    # str() of some SMTP errors includes the recipient address, which must not
    # end up in logs.
    code = getattr(e, "smtp_code", None) or getattr(e, "errno", None)
    if code is not None:
        return "%s (%s)" % (type(e).__name__, code)
    return type(e).__name__


def build_message(
    config: MailConfig, to: str, subject: str, text: str, html: str | None = None
) -> EmailMessage:
    # The SMTP policy rejects CR and LF in header values, so a value taken from
    # user input cannot add headers of its own.
    msg = EmailMessage(policy=SMTP)
    msg["From"] = config.from_address
    msg["To"] = to
    msg["Subject"] = subject
    msg["Date"] = formatdate(usegmt=True)
    # make_msgid defaults to the local hostname, which names the container.
    from_domain = parseaddr(config.from_address)[1].rpartition("@")[2]
    msg["Message-ID"] = make_msgid(domain=from_domain or None)
    msg.set_content(text)
    if html is not None:
        msg.add_alternative(html, subtype="html")
    return msg


def connect(config: MailConfig) -> smtplib.SMTP:
    context = ssl.create_default_context()
    smtp: smtplib.SMTP
    if config.security == "tls":
        smtp = smtplib.SMTP_SSL(
            config.host, config.port, timeout=config.timeout, context=context
        )
    else:
        smtp = smtplib.SMTP(config.host, config.port, timeout=config.timeout)
    try:
        if config.security == "starttls":
            # Raises SMTPNotSupportedError if the server does not offer it,
            # rather than carrying on in plain text.
            smtp.starttls(context=context)
        if config.username:
            smtp.login(config.username, config.password or "")
    except BaseException:
        smtp.close()
        raise
    return smtp


def send_mail(
    config: MailConfig, to: str, subject: str, text: str, html: str | None = None
) -> None:
    """Send one message, with an HTML alternative if html is given.

    Raises MailError if mail is not configured or the server does not take the
    message, and ValueError if to is not a single bare address or a header
    value contains a line break.
    """
    if not config.host or not config.from_address:
        raise MailError("mail is not configured")
    check_recipient(to)
    msg = build_message(config, to, subject, text, html)
    try:
        smtp = connect(config)
        try:
            smtp.send_message(msg, to_addrs=[to])
        except BaseException:
            # No QUIT: after a timeout it would wait as long again.
            smtp.close()
            raise
        # The message is already accepted at this point, so a failed QUIT must
        # not turn it into an error a caller might retry.
        try:
            smtp.quit()
        except (OSError, smtplib.SMTPException):
            smtp.close()
    except (OSError, smtplib.SMTPException, UnicodeError) as e:
        # UnicodeError comes from non-ASCII credentials, a server problem
        # rather than a bad recipient, so it must not escape as a ValueError.
        error = describe_error(e)
        logger.warning(
            "Failed to send mail via %s:%s: %s", config.host, config.port, error
        )
        raise MailError(error) from e
