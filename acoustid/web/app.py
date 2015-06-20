import os
import pickle
from flask import Flask, request, request_tearing_down, session
from flask.sessions import SecureCookieSessionInterface
from sqlalchemy.orm import scoped_session
from acoustid.script import Script
from acoustid.web import db
from acoustid.web.views.general import general_page
from acoustid.web.views.user import user_page
from acoustid.web.views.apps import apps_page
from acoustid.web.views.metadata import metadata_page
from acoustid.web.views.stats import stats_page

config_filename = os.environ['ACOUSTID_CONFIG']

script = Script(config_filename)
script.setup_logging()

config = script.config

app = Flask('acoustid.web')
app.config.update(
    DEBUG=config.website.debug,
    SECRET_KEY=config.website.secret,
    MB_OAUTH_CLIENT_ID=config.website.mb_oauth_client_id,
    MB_OAUTH_CLIENT_SECRET=config.website.mb_oauth_client_secret,
    GOOGLE_OAUTH_CLIENT_ID=config.website.google_oauth_client_id,
    GOOGLE_OAUTH_CLIENT_SECRET=config.website.google_oauth_client_secret,
)
app.acoustid_config = config

# can't use json because of python-openid
app.session_interface = SecureCookieSessionInterface()
app.session_interface.serializer = pickle

@app.context_processor
def inject_account_id():
    return dict(account_id=session.get('id'))

def get_flask_request_scope():
    return id(request._get_current_object())

@request_tearing_down.connect
def close_db_session(sender, **kwargs):
    db.session.close()

db.session_factory.configure(bind=config.database.create_engine())
db.session = scoped_session(db.session_factory, scopefunc=get_flask_request_scope)

app.register_blueprint(general_page)
app.register_blueprint(user_page)
app.register_blueprint(apps_page)
app.register_blueprint(metadata_page)
app.register_blueprint(stats_page)

if __name__ == "__main__":
    import argparse
    from werkzeug.serving import run_simple

    parser = argparse.ArgumentParser()
    parser.add_argument('--proxy', action='store_true')
    parser.add_argument('--ssl', action='store_true')
    parser.add_argument('--ssl-crt')
    parser.add_argument('--ssl-key')
    args = parser.parse_args()

    app.debug = True

    run_args = {
        'use_debugger': True,
        'use_reloader': True,
        'extra_files': [config_filename],
    }

    if args.ssl:
        if args.ssl_crt and args.ssl_key:
            run_args['ssl_context'] = args.ssl_crt, args.ssl_key
        else:
            run_args['ssl_context'] = 'adhoc'
        #import ssl
        #context = ssl.SSLContext(ssl.PROTOCOL_TLSv1_2)
        #context.load_cert_chain(args.ssl_crt, args.ssl_key)
        #run_args['ssl_context'] = context

    if args.proxy:
        from werkzeug.contrib.fixers import ProxyFix
        app = ProxyFix(app)

    script.setup_console_logging()
    run_simple('127.0.0.1', 5000, app, **run_args)
