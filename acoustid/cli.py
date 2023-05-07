import importlib
import os
from typing import Optional

import click

from acoustid.cron import run_cron
from acoustid.script import Script
from acoustid.scripts.import_submissions import run_import
from acoustid.worker import run_worker
from acoustid.wsgi_utils import run_api_app, run_web_app


@click.group()
def cli():
    # type: () -> None
    pass


@cli.group()
def run():
    # type: () -> None
    pass


@run.command("web")
@click.option("-c", "--config", default="acoustid.conf", envvar="ACOUSTID_CONFIG")
@click.option("-w", "--workers", type=int)
@click.option("-t", "--threads", type=int)
def run_web_cmd(config, workers=None, threads=None):
    # type: (str, Optional[int], Optional[int]) -> None
    """Run production uWSGI with the website."""
    os.environ["ACOUSTID_CONFIG"] = config
    script = Script(config)
    script.setup_console_logging()
    script.setup_sentry()
    run_web_app(script.config, workers=workers, threads=threads)


@run.command("api")
@click.option("-c", "--config", default="acoustid.conf", envvar="ACOUSTID_CONFIG")
@click.option("-w", "--workers", type=int)
@click.option("-t", "--threads", type=int)
def run_api_cmd(config, workers=None, threads=None):
    # type: (str, Optional[int], Optional[int]) -> None
    """Run production uWSGI with the API."""
    os.environ["ACOUSTID_CONFIG"] = config
    script = Script(config)
    script.setup_console_logging()
    script.setup_sentry()
    run_api_app(script.config, workers=workers, threads=threads)


@run.command("cron")
@click.option("-c", "--config", default="acoustid.conf", envvar="ACOUSTID_CONFIG")
def run_cron_cmd(config: str) -> None:
    """Run cron."""
    script = Script(config)
    script.setup_console_logging()
    script.setup_sentry()
    run_cron(script)


@run.command("worker")
@click.option("-c", "--config", default="acoustid.conf", envvar="ACOUSTID_CONFIG")
def run_worker_cmd(config: str) -> None:
    """Run worker."""
    script = Script(config)
    script.setup_console_logging()
    script.setup_sentry()
    run_worker(script)


@run.command("import")
@click.option("-c", "--config", default="acoustid.conf", envvar="ACOUSTID_CONFIG")
def run_import_cmd(config):
    # type: (str) -> None
    """Run import."""
    script = Script(config)
    script.setup_console_logging(verbose=True)
    script.setup_sentry()
    run_import(script)


@run.command("script")
@click.argument("name")
@click.option("-c", "--config", default="acoustid.conf", envvar="ACOUSTID_CONFIG")
def run_script_cmd(name, config):
    # type: (str, str) -> None
    """Run a built-in script."""
    script = Script(config)
    script.setup_console_logging()
    script.setup_sentry()
    mod = importlib.import_module("acoustid.scripts.{}".format(name))
    func_name = "run_{}".format(name)
    func = getattr(mod, func_name)
    func(script, None, None)


@cli.command("shell")
@click.option("-c", "--config", default="acoustid.conf", envvar="ACOUSTID_CONFIG")
def shell_cmd(config):
    # type: (str) -> None
    """Run shell."""
    import IPython

    script = Script(config)
    script.setup_console_logging()
    script.setup_sentry()
    with script.context() as ctx:
        _ = ctx
        IPython.embed()


def main():
    # type: () -> None
    cli()
