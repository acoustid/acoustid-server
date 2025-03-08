import datetime
import json
import logging

from acoustid.tracing import get_trace_id

DEFAULT_LOG_RECORD_KEYS = set(logging.makeLogRecord({}).__dict__.keys())


class JsonLogFormatter(logging.Formatter):
    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:
        return (
            datetime.datetime.fromtimestamp(record.created)
            .astimezone()
            .isoformat(timespec="milliseconds")
        )

    def format(self, record: logging.LogRecord) -> str:
        message = {
            "time": self.formatTime(record),
            "level": record.levelname.lower(),
            "message": record.getMessage(),
        }
        if record.exc_info:
            message["exception"] = self.formatException(record.exc_info)
        trace_id = get_trace_id()
        if trace_id:
            message["trace_id"] = trace_id
        for key, value in record.__dict__.items():
            if key not in message:
                if key not in DEFAULT_LOG_RECORD_KEYS:
                    message[key] = value
        return json.dumps(message)
