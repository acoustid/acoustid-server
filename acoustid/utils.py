# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import base64
import datetime
import hmac
import os
import re
from logging import Handler

from urllib.parse import urlencode
from urllib.request import urlopen


def generate_api_key(length=10) -> str:
    random_bytes = os.urandom(20)
    return re.sub("[/+=]", "", base64.b64encode(random_bytes).decode("ascii").strip())[
        :length
    ]


def generate_demo_client_api_key(secret, day=None):
    if day is None:
        day = datetime.date.today()
    key = "{}:demo-client-api-key".format(secret).encode("utf8")
    message = "{:x}".format(day.toordinal()).encode("utf8")
    digest = hmac.new(key, message, "md5").digest()[:8]
    encoded_digest = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    api_key = list(encoded_digest)
    api_key[-2] = "A"
    return "".join(api_key)


def check_demo_client_api_key(secret, api_key, max_age=7):
    if len(api_key) == 11 and api_key[-2] == "A":
        day = datetime.date.today()
        for i in range(max_age):
            if api_key == generate_demo_client_api_key(secret, day):
                return True
            day += datetime.timedelta(days=1)
    return False


def is_uuid(s):
    """
    Check whether the given string is a valid UUID
    """
    return bool(re.match(r"^[0-9a-fA-F]{8}(-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}$", s))


def is_int(s):
    try:
        int(s)
    except ValueError:
        return False
    return True


def is_foreignid(s):
    return bool(re.match(r"^[0-9a-z]+:.+$", s))


def singular(plural):
    """
    Take a plural English word and turn it into singular

    Obviously, this doesn't work in general. It know just enough words to
    generate XML tag names for list items. For example, if we have an element
    called 'tracks' in the response, it will be serialized as a list without
    named items in JSON, but we need names for items in XML, so those will be
    called 'track'.
    """
    if plural.endswith("ies"):
        return plural[:-3] + "y"
    if plural.endswith("s"):
        return plural[:-1]
    raise ValueError("unknown plural form %r" % (plural,))


def call_internal_api(config, func, **kwargs):
    url = config.cluster.base_master_url.rstrip("/") + "/v2/internal/" + func
    data = dict(kwargs)
    data["secret"] = config.cluster.secret
    urlopen(url, urlencode(data))
