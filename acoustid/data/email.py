# Copyright (C) 2026 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

"""Email addresses on accounts and the links that confirm them.

An address only reaches the account row once its owner has opened a
confirmation link, so account.email is always a verified address. Until then
the pending address is in account_email_confirmation, under a hash of the
link's token, for CONFIRMATION_TTL; the link works once.
"""

import datetime
import hashlib
import hmac
import logging
import secrets
from dataclasses import dataclass

from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy import sql
from sqlalchemy.exc import IntegrityError

from acoustid import tables as schema
from acoustid.db import AppDB, pg_advisory_xact_lock
from acoustid.mail import check_recipient
from acoustid.utils import generate_api_key

logger = logging.getLogger(__name__)

CONFIRMATION_TTL = datetime.timedelta(minutes=15)

# Confirmation emails per hour, per account and per address. The second limit
# is what stops someone flooding an inbox that is not theirs.
MAX_EMAILS_PER_ACCOUNT_PER_HOUR = 5
MAX_EMAILS_PER_ADDRESS_PER_HOUR = 3
# Accounts are free to make, so per account alone is not much of a limit.
MAX_EMAILS_PER_IP_PER_HOUR = 10
RATE_LIMIT_PREFIX = "emailrate:"


def normalize_email(value: str) -> str | None:
    """The address as stored and sent to, or None if it is not one we accept.

    Lowercased as a whole. The local part is case-sensitive in theory, but no
    mail provider treats it that way, and a case-insensitive address is what
    lets the unique index mean one account per address.
    """
    email = value.strip().lower()
    # Non-ASCII addresses need SMTPUTF8 from every server on the way, and
    # have several spellings that would each pass the unique index.
    if len(email) > 254 or not email.isascii():
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


def create_email_confirmation(conn: AppDB, account_id: int, email: str) -> str:
    """Returns the token for the link. Only its hash is stored."""
    token = secrets.token_urlsafe(32)
    table = schema.account_email_confirmation
    conn.execute(
        table.insert().values(
            token_hash=hash_token(token),
            account_id=account_id,
            email=email,
            expires=sql.func.now() + CONFIRMATION_TTL,
        )
    )
    return token


def get_email_confirmation(conn: AppDB, token: str) -> EmailConfirmation | None:
    """Look without using the link up, for the page that asks to confirm."""
    if not token:
        return None
    table = schema.account_email_confirmation
    stmt = (
        sql.select(table.c.account_id, table.c.email)
        .where(table.c.token_hash == hash_token(token))
        .where(table.c.expires > sql.func.now())
    )
    row = conn.execute(stmt).first()
    if row is None:
        return None
    return EmailConfirmation(account_id=row.account_id, email=row.email)


def consume_email_confirmation(conn: AppDB, token: str, account_id: int) -> str | None:
    """Use the link up and return its address, if it is live and was sent for
    this account. Of two concurrent requests, only one gets it; if the
    transaction rolls back, the link is still there."""
    if not token:
        return None
    table = schema.account_email_confirmation
    stmt = (
        table.delete()
        .where(table.c.token_hash == hash_token(token))
        .where(table.c.account_id == account_id)
        .where(table.c.expires > sql.func.now())
        .returning(table.c.email)
    )
    return conn.execute(stmt).scalar()


def delete_expired_email_confirmations(conn: AppDB) -> int:
    table = schema.account_email_confirmation
    stmt = table.delete().where(table.c.expires < sql.func.now())
    return conn.execute(stmt).rowcount


def within_hourly_limits(redis: Redis, limits: list[tuple[str, int]]) -> bool:
    """Count one email against each (name, limit). False if any limit is
    reached, in which case the email must not be sent.

    The counts are only a brake. If redis is unavailable, or loses them, more
    emails get through for a while, so this allows the email rather than fail.

    Each key is counted on its own: redis sits behind a proxy that shards
    keys, so nothing here may span two keys. The window is the clock hour,
    in the key name, so repeated attempts cannot keep extending it, and a key
    that missed its EXPIRE still stops counting when the hour ends.
    """
    hour = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d%H")
    allowed = True
    for name, limit in limits:
        key = "%s%s:%s" % (RATE_LIMIT_PREFIX, name, hour)
        try:
            pipe = redis.pipeline()
            pipe.incr(key)
            pipe.expire(key, 3600)
            count = pipe.execute()[0]
        except RedisError:
            logger.warning("Failed to count emails", exc_info=True)
            continue
        if count > limit:
            allowed = False
    return allowed


def within_global_limits(redis: Redis, max_per_hour: int, max_per_day: int) -> bool:
    """Count one email against the site-wide caps (0 for none). False if one
    is reached, in which case the email must not be sent.

    Call it last, once nothing else stops the email: only emails that would
    really go out may count, or refused requests could use the cap up for
    everyone. Like the other limits, this fails open without redis.
    """
    now = datetime.datetime.now(datetime.timezone.utc)
    caps = [
        ("global:hour:" + now.strftime("%Y%m%d%H"), max_per_hour, 3600),
        ("global:day:" + now.strftime("%Y%m%d"), max_per_day, 86400),
    ]
    # Stops at the first cap that refuses, so the emails the hourly cap
    # turns away do not count towards the day's.
    for name, limit, ttl in caps:
        if not limit:
            continue
        key = RATE_LIMIT_PREFIX + name
        try:
            pipe = redis.pipeline()
            pipe.incr(key)
            pipe.expire(key, ttl)
            count = pipe.execute()[0]
        except RedisError:
            logger.warning("Failed to count emails", exc_info=True)
            continue
        if count > limit:
            if count == limit + 1:
                logger.warning("Site-wide email cap reached: %s (%d)", name, limit)
            return False
    return True


def address_limit(secret: str, email: str) -> tuple[str, int]:
    # Keyed by an HMAC, so the key does not reveal the address, even to
    # someone hashing a list of candidate addresses. Shared by every kind of
    # email, since the point is the recipient's inbox.
    address = hmac.new(secret.encode(), email.encode(), hashlib.sha256).hexdigest()
    return ("address:" + address, MAX_EMAILS_PER_ADDRESS_PER_HOUR)


def ip_limit(ip: str) -> tuple[str, int]:
    return ("ip:" + ip, MAX_EMAILS_PER_IP_PER_HOUR)


def count_email_sent(
    redis: Redis, secret: str, account_id: int, email: str, ip: str
) -> bool:
    """Count one confirmation email, see within_hourly_limits."""
    return within_hourly_limits(
        redis,
        [
            ("account:%d" % account_id, MAX_EMAILS_PER_ACCOUNT_PER_HOUR),
            address_limit(secret, email),
            ip_limit(ip),
        ],
    )


def count_signin_email_sent(redis: Redis, secret: str, email: str, ip: str) -> bool:
    """Count one sign-in email, see within_hourly_limits."""
    return within_hourly_limits(redis, [address_limit(secret, email), ip_limit(ip)])


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


SIGNIN_TTL = datetime.timedelta(minutes=15)

# Wrong codes one sign-in request takes before it is dead, link included.
MAX_CODE_ATTEMPTS = 5

# Limits per address that hold even when redis does not, counted from the
# rows themselves. A code is one in a million; with these, someone guessing
# at an address gets at most MAX_WRONG_CODES_PER_ADDRESS_PER_DAY tries a day,
# however many emails they make it send. Past that the codes stop working,
# but the links do not, so the owner of the address is not locked out.
MAX_SIGNINS_PER_ADDRESS_PER_HOUR = 3
MAX_WRONG_CODES_PER_ADDRESS_PER_DAY = 20
SIGNIN_RETENTION = datetime.timedelta(days=1)


class TooManyWrongCodes(Exception):
    """Codes for this address are refused for now; links still work."""


def hash_code(secret: str, token_hash: str, code: str) -> str:
    message = (token_hash + ":" + code).encode()
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def normalize_code(value: str) -> str:
    return "".join(c for c in value if c.isdigit())


@dataclass(frozen=True)
class EmailSignin:
    id: int
    token: str
    code: str


def create_email_signin(
    conn: AppDB, secret: str, email: str, return_url: str | None
) -> EmailSignin:
    token = secrets.token_urlsafe(32)
    code = "%06d" % secrets.randbelow(1000000)
    token_hash = hash_token(token)
    table = schema.account_email_signin
    stmt = (
        table.insert()
        .values(
            token_hash=token_hash,
            code_hash=hash_code(secret, token_hash, code),
            email=email,
            return_url=return_url,
            expires=sql.func.now() + SIGNIN_TTL,
        )
        .returning(table.c.id)
    )
    return EmailSignin(id=conn.execute(stmt).scalar_one(), token=token, code=code)


def live_signin(table: sql.TableClause) -> sql.ColumnElement[bool]:
    return sql.and_(
        table.c.used.is_(None),
        table.c.expires > sql.func.now(),
        table.c.code_attempts < MAX_CODE_ATTEMPTS,
    )


def get_email_signin_by_token(conn: AppDB, token: str) -> str | None:
    """The address of a live sign-in link, without using it up."""
    if not token:
        return None
    table = schema.account_email_signin
    stmt = (
        sql.select(table.c.email)
        .where(table.c.token_hash == hash_token(token))
        .where(live_signin(table))
    )
    return conn.execute(stmt).scalar()


@dataclass(frozen=True)
class UsedSignin:
    email: str
    return_url: str | None


def consume_email_signin_by_token(conn: AppDB, token: str) -> UsedSignin | None:
    """Use a sign-in link up, and with it the code.

    The row stays, marked used, for the per-address limits to count."""
    if not token:
        return None
    table = schema.account_email_signin
    stmt = (
        table.update()
        .where(table.c.token_hash == hash_token(token))
        .where(live_signin(table))
        .values(used=sql.func.now())
        .returning(table.c.email, table.c.return_url)
    )
    row = conn.execute(stmt).first()
    if row is None:
        return None
    return UsedSignin(email=row.email, return_url=row.return_url)


def get_email_signin_address(conn: AppDB, id: int) -> str | None:
    """The address of a live sign-in request, for the page asking for its code."""
    table = schema.account_email_signin
    stmt = sql.select(table.c.email).where(table.c.id == id).where(live_signin(table))
    return conn.execute(stmt).scalar()


def signin_allowed(conn: AppDB, email: str) -> bool:
    """Whether another sign-in email may go to this address this hour.

    Takes a lock on the address until the transaction ends, so that of two
    concurrent requests only one can see room under the limit. The caller
    inserts its request and commits while holding it.
    """
    pg_advisory_xact_lock(conn, "account_email_signin", email)
    table = schema.account_email_signin
    stmt = (
        sql.select(sql.func.count())
        .where(table.c.email == email)
        .where(table.c.created > sql.func.now() - datetime.timedelta(hours=1))
    )
    return conn.execute(stmt).scalar_one() < MAX_SIGNINS_PER_ADDRESS_PER_HOUR


def wrong_codes_today(conn: AppDB, email: str) -> int:
    table = schema.account_email_signin
    stmt = (
        sql.select(sql.func.coalesce(sql.func.sum(table.c.code_attempts), 0))
        .where(table.c.email == email)
        .where(table.c.created > sql.func.now() - SIGNIN_RETENTION)
    )
    return conn.execute(stmt).scalar_one()


def consume_email_signin_by_code(
    conn: AppDB, secret: str, ids: list[int], code: str
) -> UsedSignin | None:
    """Use a sign-in request up by its code, and with it the link.

    ids are the requests this browser made, newest last, so the code from an
    earlier email still works after asking for another. Only those for the
    same address as the newest are tried, so every guess is charged to the
    address it is a guess at. Using one uses them all up; the rows stay,
    marked used, for the per-address limits to count. A wrong code counts
    against the newest, and the caller must commit even then, or the count
    is lost. The rows are locked while they are checked, so concurrent
    guesses are counted one after another.

    Raises TooManyWrongCodes if the address has had too many today.
    """
    if not ids:
        return None
    table = schema.account_email_signin
    newest_email = conn.execute(
        sql.select(table.c.email)
        .where(table.c.id.in_(ids))
        .where(live_signin(table))
        .order_by(table.c.id.desc())
        .limit(1)
    ).scalar()
    if newest_email is None:
        return None
    # Other browsers may hold requests for the same address. The address
    # lock, held until the caller commits, makes their guesses see each
    # other's counts. It is taken before the row locks; the link path takes
    # only row locks, so the two cannot deadlock.
    pg_advisory_xact_lock(conn, "account_email_signin", newest_email)
    stmt = (
        sql.select(
            table.c.id,
            table.c.email,
            table.c.token_hash,
            table.c.code_hash,
            table.c.return_url,
        )
        .where(table.c.id.in_(ids))
        .where(table.c.email == newest_email)
        .where(live_signin(table))
        .order_by(table.c.id)
        .with_for_update()
    )
    rows = conn.execute(stmt).fetchall()
    if not rows:
        return None
    newest = rows[-1]
    if wrong_codes_today(conn, newest.email) >= MAX_WRONG_CODES_PER_ADDRESS_PER_DAY:
        raise TooManyWrongCodes()
    code = normalize_code(code)
    for row in rows:
        expected = hash_code(secret, row.token_hash, code)
        if hmac.compare_digest(expected, row.code_hash):
            conn.execute(
                table.update()
                .where(table.c.id.in_([r.id for r in rows]))
                .values(used=sql.func.now())
            )
            return UsedSignin(email=row.email, return_url=row.return_url)
    conn.execute(
        table.update()
        .where(table.c.id == newest.id)
        .values(code_attempts=table.c.code_attempts + 1)
    )
    return None


def delete_expired_email_signins(conn: AppDB) -> int:
    table = schema.account_email_signin
    stmt = table.delete().where(table.c.created < sql.func.now() - SIGNIN_RETENTION)
    return conn.execute(stmt).rowcount


# The name of an account made by signing in by email. Accounts are shown by
# their MusicBrainz name or as user<id>, not by this.
EMAIL_ACCOUNT_NAME = "Email Account"


def find_or_create_email_account(conn: AppDB, email: str, ip: str | None) -> int:
    """The account with this verified address, made if there is none.

    The address is verified: whoever calls this has just used a link or code
    sent to it.
    """
    account_id = find_account_by_email(conn, email)
    if account_id is not None:
        return account_id
    account = schema.account
    stmt = (
        account.insert()
        .values(
            name=EMAIL_ACCOUNT_NAME,
            apikey=generate_api_key(),
            created_from=ip or None,
            lastlogin=sql.func.now(),
        )
        .returning(account.c.id)
    )
    savepoint = conn.begin_nested()
    account_id = conn.execute(stmt).scalar_one()
    if set_account_email(conn, account_id, email):
        savepoint.commit()
        return account_id
    # Another request made an account with the address first. Drop ours.
    savepoint.rollback()
    account_id = find_account_by_email(conn, email)
    assert account_id is not None
    return account_id
