import os
import click
from typing import Optional
from acoustid.script import Script
from acoustid.wsgi_utils import run_web_app, run_api_app
from acoustid.cron import run_cron
from acoustid.scripts.import_submissions import run_import


@click.group()
def cli():
    # type: () -> None
    pass


@cli.group()
def run():
    # type: () -> None
    pass


@run.command('web')
@click.option('-c', '--config', default='acoustid.conf', envvar='ACOUSTID_CONFIG')
@click.option('-w', '--workers', type=int)
@click.option('-t', '--threads', type=int)
def run_web_cmd(config, workers=None, threads=None):
    # type: (str, Optional[int], Optional[int]) -> None
    """Run production uWSGI with the website."""
    os.environ['ACOUSTID_CONFIG'] = config
    script = Script(config)
    script.setup_console_logging()
    script.setup_sentry()
    run_web_app(script.config, workers=workers, threads=threads)


@run.command('api')
@click.option('-c', '--config', default='acoustid.conf', envvar='ACOUSTID_CONFIG')
@click.option('-w', '--workers', type=int)
@click.option('-t', '--threads', type=int)
def run_api_cmd(config, workers=None, threads=None):
    # type: (str, Optional[int], Optional[int]) -> None
    """Run production uWSGI with the API."""
    os.environ['ACOUSTID_CONFIG'] = config
    script = Script(config)
    script.setup_console_logging()
    script.setup_sentry()
    run_api_app(script.config, workers=workers, threads=threads)


@run.command('cron')
@click.option('-c', '--config', default='acoustid.conf', envvar='ACOUSTID_CONFIG')
def run_cron_cmd(config):
    # type: (str) -> None
    """Run cron."""
    script = Script(config)
    script.setup_console_logging()
    script.setup_sentry()
    run_cron(script)


@run.command('import')
@click.option('-c', '--config', default='acoustid.conf', envvar='ACOUSTID_CONFIG')
def run_import_cmd(config):
    # type: (str) -> None
    """Run import."""
    script = Script(config)
    script.setup_console_logging()
    script.setup_sentry()
    run_import(script)


@cli.command('shell')
@click.option('-c', '--config', default='acoustid.conf', envvar='ACOUSTID_CONFIG')
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
