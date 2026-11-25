# Copyright (C) 2026 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

"""Email addresses on accounts and the links that confirm them.

An address only reaches the account row once its owner has opened a
confirmation link, so account.email is always a verified address. Until then
the pending address lives in redis, under a hash of the link's token, for
CONFIRMATION_TTL seconds; the link works once.
"""

import hashlib
import json
import secrets
from dataclasses import dataclass

from redis import Redis
from sqlalchemy import sql
from sqlalchemy.exc import IntegrityError

from acoustid import tables as schema
from acoustid.db import AppDB
from acoustid.mail import check_recipient

CONFIRMATION_TTL = 15 * 60
CONFIRMATION_PREFIX = "emailconfirm:"

# Confirmation emails per hour, per account and per address. The second limit
# is what stops someone flooding an inbox that is not theirs.
MAX_EMAILS_PER_ACCOUNT_PER_HOUR = 5
MAX_EMAILS_PER_ADDRESS_PER_HOUR = 3
RATE_LIMIT_PREFIX = "emailrate:"


def normalize_email(value: str) -> str | None:
    """The address as stored and sent to, or None if it is not one we accept.

    Lowercased as a whole. The local part is case-sensitive in theory, but no
    mail provider treats it that way, and a case-insensitive address is what
    lets the unique index mean one account per address.
    """
    email = value.strip().lower()
    if len(email) > 254:
        return None
    try:
        check_recipient(email)
    except ValueError:
        return None
    local, _, domain = email.partition("@")
    labels = domain.split(".")
    if len(local) > 64 or len(labels) < 2 or not all(labels):
        return None
    return email


def mask_email(email: str) -> str:
    """For showing an address back to its owner without printing it whole."""
    local, _, domain = email.partition("@")
    if len(local) <= 2:
        masked = local[:1] + "•••"
    else:
        masked = local[0] + "•••" + local[-1]
    return masked + "@" + domain


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class EmailConfirmation:
    account_id: int
    email: str


def create_email_confirmation(redis: Redis, account_id: int, email: str) -> str:
    """Returns the token for the link. Only its hash is stored."""
    token = secrets.token_urlsafe(32)
    value = json.dumps({"account_id": account_id, "email": email})
    redis.set(CONFIRMATION_PREFIX + hash_token(token), value, ex=CONFIRMATION_TTL)
    return token


def parse_confirmation(value: bytes | str | None) -> EmailConfirmation | None:
    if value is None:
        return None
    data = json.loads(value)
    return EmailConfirmation(account_id=data["account_id"], email=data["email"])


def get_email_confirmation(redis: Redis, token: str) -> EmailConfirmation | None:
    """Look without using the link up, for the page that asks to confirm."""
    if not token:
        return None
    return parse_confirmation(redis.get(CONFIRMATION_PREFIX + hash_token(token)))


def consume_email_confirmation(redis: Redis, token: str) -> EmailConfirmation | None:
    """Use the link up. Of two concurrent requests, only one gets it."""
    if not token:
        return None
    return parse_confirmation(redis.getdel(CONFIRMATION_PREFIX + hash_token(token)))


def count_email_sent(redis: Redis, account_id: int, email: str) -> bool:
    """Count one confirmation email. False if either hourly limit is reached,
    in which case the email must not be sent."""
    # The address is hashed so the key does not hold it.
    keys = [
        (
            RATE_LIMIT_PREFIX + "account:%d" % account_id,
            MAX_EMAILS_PER_ACCOUNT_PER_HOUR,
        ),
        (
            RATE_LIMIT_PREFIX + "address:" + hash_token(email),
            MAX_EMAILS_PER_ADDRESS_PER_HOUR,
        ),
    ]
    pipe = redis.pipeline()
    for key, _ in keys:
        pipe.incr(key)
        pipe.expire(key, 3600, nx=True)
    counts = pipe.execute()[::2]
    return all(count <= limit for count, (_, limit) in zip(counts, keys))


def find_account_by_email(conn: AppDB, email: str) -> int | None:
    account = schema.account
    stmt = (
        sql.select(account.c.id)
        .where(account.c.email == email)
        .where(account.c.email_verified.is_not(None))
    )
    return conn.execute(stmt).scalar()


def set_account_email(conn: AppDB, account_id: int, email: str) -> bool:
    """Record a confirmed address. False if another account already has it.

    The unique index is what decides, so two accounts confirming the same
    address at once cannot both get it. The update runs in a savepoint, so a
    refusal leaves the caller's transaction usable.
    """
    account = schema.account
    stmt = (
        account.update()
        .where(account.c.id == account_id)
        .values(email=email, email_verified=sql.func.now())
    )
    try:
        with conn.begin_nested():
            conn.execute(stmt)
    except IntegrityError:
        return False
    return True
