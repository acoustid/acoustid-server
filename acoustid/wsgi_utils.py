import six
import datetime
import logging
import signal
import io
import os
import sys
from typing import List, Callable, Optional
from acoustid.config import Config
if six.PY3:
    import subprocess
else:
    import subprocess32 as subprocess

logger = logging.getLogger(__name__)


def call_setpgrp():
    os.setpgrp()


class ProcessWrapper(object):

    def __init__(self, args, shutdown_handler=None, shutdown_delay=0.0):
        # type: (List[six.text_type], Callable[[], None], float) -> None
        self.name = args[0]
        self.shutdown = False
        self.shutdown_requested_at = None
        self.shutdown_handler = shutdown_handler
        self.shutdown_handler_called = False
        self.shutdown_delay = datetime.timedelta(seconds=shutdown_delay)
        self.stop_immediately = False
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)
        logger.info('Starting %s', subprocess.list2cmdline(args))
        self.process = subprocess.Popen(args, preexec_fn=call_setpgrp)

    def _handle_signal(self, sig, frame):
        logger.info('Received signal %s', sig)
        if self.shutdown:
            if not self.stop_immediately:
                logger.info('Will stop gunicorn ASAP')
                self.stop_immediately = True
        else:
            self.shutdown = True
            self.shutdown_requested_at = datetime.datetime.now()

    def wait(self):
        # type: () -> int
        while True:
            try:
                return self.process.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                pass

            if not self.shutdown:
                continue

            if not self.shutdown_handler_called:
                logger.info('Preparing to shut down, will stop gunicorn in %s seconds', self.shutdown_delay.total_seconds())
                if self.shutdown_handler:
                    self.shutdown_handler()
                self.shutdown_handler_called = True

            assert self.shutdown_requested_at is not None
            if self.stop_immediately or (datetime.datetime.now() > self.shutdown_requested_at + self.shutdown_delay):
                logger.info('Stopping %s', self.name)
                self.process.terminate()


def is_shutting_down(shutdown_file_path):
    # type: (six.text_type) -> bool
    return os.path.exists(shutdown_file_path)


def shutdown_handler(shutdown_file_path):
    # type: (six.text_type) -> None
    if not is_shutting_down(shutdown_file_path):
        with io.open(shutdown_file_path, 'wt', encoding='utf8') as fp:
            fp.write(u'shutdown')


def cleanup_shutdown_file(shutdown_file_path):
    # type: (six.text_type) -> None
    try:
        os.remove(shutdown_file_path)
    except OSError as e:
        if e.errno != 2:
            raise


def run_gunicorn(config, args):
    # type: (Config, List[six.text_type]) -> int
    cleanup_shutdown_file(config.website.shutdown_file_path)
    try:
        wrapper = ProcessWrapper(
            args,
            shutdown_handler=lambda: shutdown_handler(config.website.shutdown_file_path),
            shutdown_delay=config.website.shutdown_delay)
        return wrapper.wait()
    finally:
        cleanup_shutdown_file(config.website.shutdown_file_path)


def common_gunicorn_args(config, workers=None, threads=None):
    # type: (Config, Optional[int], Optional[int]) -> List[six.text_type]
    args = [
      os.path.join(sys.prefix, "bin", "gunicorn"),
      "--workers", six.text_type(workers or config.gunicorn.workers),
      "--threads", six.text_type(threads or config.gunicorn.threads),
      "--limit-request-line", "8190",
    ]
    if config.gunicorn.timeout:
        args.extend(["--timeout", six.text_type(config.gunicorn.timeout)])
    if config.gunicorn.backlog:
        args.extend(["--backlog", six.text_type(config.gunicorn.backlog)])
    if config.statsd.enabled:
        args.extend(["--statsd-host", "{}:{}".format(config.statsd.host, config.statsd.port)])
    return args


def run_api_app(config, workers=None, threads=None):
    # type: (Config, Optional[int], Optional[int]) -> int
    args = common_gunicorn_args(config, workers=workers, threads=threads) + [
      "--bind", "0.0.0.0:3031",
      "acoustid.server:make_application()",
    ]
    if config.statsd.enabled:
        args.extend(["--statsd-prefix", "{}service.api".format(config.statsd.prefix)])
    return run_gunicorn(config, args)


def run_web_app(config, workers=None, threads=None):
    # type: (Config, Optional[int], Optional[int]) -> int
    args = common_gunicorn_args(config, workers=workers, threads=threads) + [
      "--bind", "0.0.0.0:3032",
      "acoustid.web.app:make_application()",
    ]
    if config.statsd.enabled:
        args.extend(["--statsd-prefix", "{}service.web".format(config.statsd.prefix)])
    return run_gunicorn(config, args)
