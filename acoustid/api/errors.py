# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details. 

import logging

logger = logging.getLogger(__name__)


ERROR_UNKNOWN_FORMAT = 1
ERROR_MISSING_PARAMETER = 2
ERROR_INVALID_FINGERPRINT = 3
ERROR_INVALID_APIKEY = 4
ERROR_INTERNAL = 5
ERROR_INVALID_USER_APIKEY = 6


class WebServiceError(Exception):

    def __init__(self, code, message):
        self.code = code
        self.message = message


class UnknownFormatError(WebServiceError):

    def __init__(self, name):
        message = 'unknown format "%s"' % (name,)
        WebServiceError.__init__(self, ERROR_UNKNOWN_FORMAT, message)


class MissingParameterError(WebServiceError):

    def __init__(self, name):
        message = 'missing required parameter "%s"' % (name,)
        WebServiceError.__init__(self, ERROR_MISSING_PARAMETER, message)
        self.parameter = name


class InvalidFingerprintError(WebServiceError):

    def __init__(self):
        message = 'invalid fingerprint'
        WebServiceError.__init__(self, ERROR_INVALID_FINGERPRINT, message)


class InvalidAPIKeyError(WebServiceError):

    def __init__(self):
        message = 'invalid API key'
        WebServiceError.__init__(self, ERROR_INVALID_APIKEY, message)


class InvalidUserAPIKeyError(WebServiceError):

    def __init__(self):
        message = 'invalid user API key'
        WebServiceError.__init__(self, ERROR_INVALID_USER_APIKEY, message)


class InternalError(WebServiceError):

    def __init__(self):
        message = 'internal error'
        WebServiceError.__init__(self, ERROR_INTERNAL, message)

