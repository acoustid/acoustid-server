# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import re
import syslog
import urllib
import urllib2
import hashlib
import time
import datetime
import hmac
import base64
from logging import Handler
from logging.handlers import SysLogHandler


def generate_api_key(length=10):
    return re.sub('[/+=]', '', hashlib.sha1(str(time.time())).digest().encode('base64').strip())[:length]


def generate_demo_client_api_key(secret, day=None):
    if day is None:
        day = datetime.date.today()
    key = '{}:demo-client-api-key'.format(secret)
    message = '{:x}'.format(day.toordinal())
    api_key = list(base64.urlsafe_b64encode(hmac.new(key, message).digest()[:8]).rstrip('='))
    api_key[-2] = 'A'
    return ''.join(api_key)


def check_demo_client_api_key(secret, api_key, max_age=7):
    if len(api_key) == 11 and api_key[-2] == 'A':
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
    return bool(re.match(r'^[0-9a-fA-F]{8}(-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}$', s))


def is_int(s):
    try:
        int(s)
    except ValueError:
        return False
    return True


def is_foreignid(s):
    return bool(re.match(r'^[0-9a-z]+:.+$', s))


def singular(plural):
    """
    Take a plural English word and turn it into singular

    Obviously, this doesn't work in general. It know just enough words to
    generate XML tag names for list items. For example, if we have an element
    called 'tracks' in the response, it will be serialized as a list without
    named items in JSON, but we need names for items in XML, so those will be
    called 'track'.
    """
    if plural.endswith('ies'):
        return plural[:-3] + 'y'
    if plural.endswith('s'):
        return plural[:-1]
    raise ValueError('unknown plural form %r' % (plural,))


def provider(value):
    """
    Returns a function that returns the given value.
    """
    def func():
        return value
    return func


class LocalSysLogHandler(Handler):
    """
    Logging handler that logs to the local syslog using the syslog module
    """

    facility_names = {
        "auth":     syslog.LOG_AUTH,
        "cron":     syslog.LOG_CRON,
        "daemon":   syslog.LOG_DAEMON,
        "kern":     syslog.LOG_KERN,
        "lpr":      syslog.LOG_LPR,
        "mail":     syslog.LOG_MAIL,
        "news":     syslog.LOG_NEWS,
        "syslog":   syslog.LOG_SYSLOG,
        "user":     syslog.LOG_USER,
        "uucp":     syslog.LOG_UUCP,
        "local0":   syslog.LOG_LOCAL0,
        "local1":   syslog.LOG_LOCAL1,
        "local2":   syslog.LOG_LOCAL2,
        "local3":   syslog.LOG_LOCAL3,
        "local4":   syslog.LOG_LOCAL4,
        "local5":   syslog.LOG_LOCAL5,
        "local6":   syslog.LOG_LOCAL6,
        "local7":   syslog.LOG_LOCAL7,
    }

    priority_map = {
        "DEBUG": syslog.LOG_DEBUG,
        "INFO": syslog.LOG_INFO,
        "WARNING": syslog.LOG_WARNING,
        "ERROR": syslog.LOG_ERR,
        "CRITICAL": syslog.LOG_CRIT
    }

    def __init__(self, ident=None, facility=syslog.LOG_USER, log_pid=False):
        Handler.__init__(self)
        self.facility = facility
        if isinstance(facility, basestring):
            self.facility = self.facility_names[facility]
        options = 0
        if log_pid:
            options |= syslog.LOG_PID
        syslog.openlog(ident, options, self.facility)
        self.formatter = None

    def close(self):
        Handler.close(self)
        syslog.closelog()

    def emit(self, record):
        try:
            msg = self.format(record)
            if isinstance(msg, unicode):
                msg = msg.encode('utf-8')
            priority = self.priority_map[record.levelname]
            for m in msg.splitlines():
                syslog.syslog(self.facility | priority, m)
        except StandardError:
            self.handleError(record)


def call_internal_api(config, func, **kwargs):
    url = config.cluster.base_master_url.rstrip('/') + '/v2/internal/' + func
    data = dict(kwargs)
    data['secret'] = config.cluster.secret
    urllib2.urlopen(url, urllib.urlencode(data))
