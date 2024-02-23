logconfig_dict = {
    "version": 1,
    "disable_existing_loggers": True,
    "root": {"level": "INFO", "handlers": ["error_console"]},
    "loggers": {
        "gunicorn.error": {
            "level": "INFO",
            "handlers": ["error_console"],
            "propagate": False,
            "qualname": "gunicorn.error",
        },
        "gunicorn.access": {
            "level": "ERROR",
            "handlers": ["null"],
            "propagate": False,
            "qualname": "gunicorn.access",
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
