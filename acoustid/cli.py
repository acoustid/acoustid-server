import click
from acoustid.script import Script
from acoustid.uwsgi_utils import run_web_app, run_api_app
from acoustid.cron import run_cron
from acoustid.scripts.import_submissions import run_import


@click.group()
def cli():
    pass


@cli.group()
def run():
    pass


@run.command('web')
@click.option('-c', '--config', default='acoustid.conf', envvar='ACOUSTID_CONFIG')
@click.option('-w', '--workers', default=1, envvar='ACOUSTID_WEB_WORKERS')
def run_web_cmd(config, workers):
    """Run production uWSGI with the website."""
    script = Script(config)
    script.setup_console_logging()
    script.setup_sentry()
    run_web_app(script.config, workers=workers)


@run.command('api')
@click.option('-c', '--config', default='acoustid.conf', envvar='ACOUSTID_CONFIG')
@click.option('-w', '--workers', default=1, envvar='ACOUSTID_API_WORKERS')
def run_api_cmd(config, workers):
    """Run production uWSGI with the API."""
    script = Script(config)
    script.setup_console_logging()
    script.setup_sentry()
    run_api_app(script.config, workers=workers)


@run.command('cron')
@click.option('-c', '--config', default='acoustid.conf', envvar='ACOUSTID_CONFIG')
def run_cron_cmd(config):
    """Run cron."""
    script = Script(config)
    script.setup_console_logging()
    script.setup_sentry()
    run_cron(script)


@run.command('import')
@click.option('-c', '--config', default='acoustid.conf', envvar='ACOUSTID_CONFIG')
def run_import_cmd(config):
    """Run import."""
    script = Script(config)
    script.setup_console_logging()
    script.setup_sentry()
    run_import(script)


def main():
    cli()
