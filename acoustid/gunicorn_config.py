logconfig_dict = {
    "version": 1,
    "disable_existing_loggers": True,
    "root": {"level": "INFO", "handlers": ["error_console"]},
    "loggers": {
        "gunicorn.error": {
            "level": "INFO",
            "handlers": ["error_console"],
            "propagate": False,
            "qualname": "gunicorn.error"
        },

        "gunicorn.access": {
            "level": "INFO",
            "handlers": ["console"],
            "propagate": False,
            "qualname": "gunicorn.access"
        }
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "generic",
            "stream": "ext://sys.stdout"
        },
        "error_console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
            "stream": "ext://sys.stderr"
        },
    },
    'formatters': {
        'json': {
            'class': 'acoustid.logging.JsonLogFormatter',
        },
        "generic": {
            "format": "%(asctime)s [%(process)d] [%(levelname)s] %(message)s",
            "datefmt": "[%Y-%m-%d %H:%M:%S %z]",
            "class": "logging.Formatter"
        }
    },
}
