# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import re
import syslog
from logging import Handler
from logging.handlers import SysLogHandler


def is_uuid(s):
    """
    Check whether the given string is a valid UUID
    """
    return bool(re.match(r'^[0-9a-fA-F]{8}(-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}$', s))


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

    facility_names = SysLogHandler.facility_names

    priority_map = {
        "DEBUG": syslog.LOG_DEBUG,
        "INFO": syslog.LOG_INFO,
        "WARNING": syslog.LOG_WARNING,
        "ERROR": syslog.LOG_ERR,
        "CRITICAL": syslog.LOG_CRIT
    }

    def __init__(self, ident=None, facility=syslog.LOG_USER, log_pid=False):
        Handler.__init__(self)
        if isinstance(facility, basestring):
            facility = self.facility_names[facility]
        options = 0
        if log_pid:
            options |= syslog.LOG_PID
        syslog.openlog(ident, options, facility)
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
            syslog.syslog(priority, msg)
        except StandardError:
            self.handleError(record)

