import datetime
import json
import logging

DEFAULT_LOG_RECORD_KEYS = set(logging.makeLogRecord({}).__dict__.keys())


class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        message = {
            "time": datetime.datetime.fromtimestamp(record.created)
            .astimezone()
            .isoformat(timespec="milliseconds"),
            "level": record.levelname.lower(),
            "message": record.getMessage(),
        }
        if record.exc_info:
            message["exception"] = self.formatException(record.exc_info)
        for key, value in record.__dict__.items():
            if key not in message:
                if key not in DEFAULT_LOG_RECORD_KEYS:
                    message[key] = value
        return json.dumps(message)
