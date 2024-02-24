logconfig_dict = {
    "version": 1,
    "disable_existing_loggers": False,
    "root": {"level": "INFO", "handlers": []},
    "loggers": {
        "gunicorn.error": {
            "level": "INFO",
            "handlers": ["error_console"],
            "propagate": True,
            "qualname": "gunicorn.error",
        },
    },
    "handlers": {
        "null": {
            "class": "logging.NullHandler",
        },
        "error_console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
            "stream": "ext://sys.stderr",
        },
    },
    "formatters": {
        "json": {
            "class": "acoustid.logging.JsonLogFormatter",
        },
    },
}
