import six
import datetime
import logging
import signal
import io
import os
import sys
from typing import List, Callable
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
                logger.info('Will stop uwsgi ASAP')
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
                logger.info('Preparing to shut down, will stop uwsgi in %s seconds', self.shutdown_delay.total_seconds())
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


def run_uwsgi(config, args):
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


def common_uwsgi_args(config, workers=1):
    # type: (Config, int) -> List[six.text_type]
    args = [
      os.path.join(sys.prefix, "bin", "uwsgi"),
      "--die-on-term",
      "--chmod-socket",
      "--master",
      "--disable-logging",
      "--log-date",
      "--buffer-size", "10240",
      "--workers", six.text_type(workers),
      "--offload-threads", "1",
      "--harakiri", "60",
      "--harakiri-verbose",
      "--post-buffering", "1",
      "--enable-threads",
      "--need-app",
    ]
    if 'PYTHONPATH' in os.environ:
        args.extend(["--python-path", os.environ['PYTHONPATH']])
    if hasattr(sys, 'real_prefix'):
        args.extend(["--virtualenv", sys.prefix])
    return args


def run_api_app(config, workers=1):
    # type: (Config, int) -> int
    args = common_uwsgi_args(config) + [
      "--http-socket", "0.0.0.0:3031",
      "--module", "acoustid.wsgi",
    ]
    return run_uwsgi(config, args)


def run_web_app(config, workers=1):
    # type: (Config, int) -> int
    static_dir = os.path.join(os.path.dirname(__file__), 'web', 'static')
    args = common_uwsgi_args(config) + [
      "--http-socket", "0.0.0.0:3032",
      "--module", "acoustid.web.app:make_application()",
      "--static-map", "/static={}".format(static_dir),
      "--static-map", "/favicon.ico={}".format(os.path.join(static_dir, 'favicon.ico')),
      "--static-map", "/robots.txt={}".format(os.path.join(static_dir, 'robots.txt')),
    ]
    return run_uwsgi(config, args)
