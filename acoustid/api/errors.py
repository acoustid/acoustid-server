# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import logging
from acoustid import const

logger = logging.getLogger(__name__)


ERROR_UNKNOWN_FORMAT = 1
ERROR_MISSING_PARAMETER = 2
ERROR_INVALID_FINGERPRINT = 3
ERROR_INVALID_APIKEY = 4
ERROR_INTERNAL = 5
ERROR_INVALID_USER_APIKEY = 6
ERROR_INVALID_UUID = 7
ERROR_INVALID_DURATION = 8
ERROR_INVALID_BITRATE = 9
ERROR_INVALID_FOREIGNID = 10
ERROR_INVALID_MAX_DURATION_DIFF = 11


class WebServiceError(Exception):

    status = 400

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
        message = 'invalid user API key ("User with the API key does not exist")'
        WebServiceError.__init__(self, ERROR_INVALID_USER_APIKEY, message)


class InternalError(WebServiceError):

    status = 500

    def __init__(self):
        message = 'internal error'
        WebServiceError.__init__(self, ERROR_INTERNAL, message)


class InvalidUUIDError(WebServiceError):

    def __init__(self, name):
        message = 'parameter "%s" is not a valid UUID' % (name,)
        WebServiceError.__init__(self, ERROR_INVALID_UUID, message)
        self.parameter = name


class InvalidForeignIDError(WebServiceError):

    def __init__(self, name):
        message = 'parameter "%s" is not a valid foreign ID, it must be in the format vendor:id' % (name,)
        WebServiceError.__init__(self, ERROR_INVALID_FOREIGNID, message)
        self.parameter = name


class InvalidDurationError(WebServiceError):

    def __init__(self, name):
        message = 'parameter "%s" must be a positive integer' % (name,)
        WebServiceError.__init__(self, ERROR_INVALID_DURATION, message)
        self.parameter = name


class InvalidBitrateError(WebServiceError):

    def __init__(self, name):
        message = 'parameter "%s" must be a positive integer' % (name,)
        WebServiceError.__init__(self, ERROR_INVALID_BITRATE, message)
        self.parameter = name


class InvalidMaxDurationDiffError(WebServiceError):

    def __init__(self, name):
        message = 'parameter "%s" must be between %d and %d' % (name, 1, const.FINGERPRINT_MAX_ALLOWED_LENGTH_DIFF)
        WebServiceError.__init__(self, ERROR_INVALID_MAX_DURATION_DIFF, message)
        self.parameter = name

