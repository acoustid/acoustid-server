# Copyright (C) 2026 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

"""Outgoing mail over SMTP.

Plain SMTP keeps the code independent of the provider: switching is a config
change. Mail is sent synchronously, so the timeout in the config bounds how long
a request can wait on the server.
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
    message, and ValueError if a header value contains a line break.
    """
    if not config.host or not config.from_address:
        raise MailError("mail is not configured")
    msg = build_message(config, to, subject, text, html)
    try:
        with connect(config) as smtp:
            smtp.send_message(msg)
    except (OSError, smtplib.SMTPException) as e:
        logger.warning("Failed to send mail via %s:%s: %s", config.host, config.port, e)
        raise MailError(str(e)) from e
