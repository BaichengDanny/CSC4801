"""Application factory for Common Ground."""
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask
from werkzeug.routing import IntegerConverter


class RecordIDConverter(IntegerConverter):
    """Reject huge URL numbers before Python conversion or SQLite binding."""
    regex = r"[0-9]{1,19}"

    def __init__(self, url_map):
        super().__init__(url_map, min=1, max=2**63 - 1)


def create_app(config=None):
    app = Flask(__name__)
    app.url_map.converters['int'] = RecordIDConverter
    app.config.from_mapping(
        SECRET_KEY=os.environ.get('SECRET_KEY') or secrets.token_hex(32),
        DATABASE=os.environ.get('DATABASE', str(Path(app.instance_path) / 'recruiting.sqlite3')),
        NOW=lambda: datetime.now(timezone.utc),
        MAX_CONTENT_LENGTH=1024 * 1024,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Lax',
        SESSION_COOKIE_SECURE=os.environ.get('COOKIE_SECURE') == '1',
    )
    if config:
        app.config.update(config)
    from . import db
    db.init_app(app)
    from flask import g, render_template
    from werkzeug.exceptions import HTTPException
    from . import auth, seed, web
    from .errors import DomainError
    from .scheduling import format_time, now_timestamp
    app.register_blueprint(auth.bp)
    app.register_blueprint(web.bp)
    app.before_request(auth.load_user)
    seed.init_app(app)
    app.jinja_env.filters['datetime'] = format_time
    app.jinja_env.globals['csrf_token'] = auth.csrf_token

    @app.context_processor
    def template_context():
        return {'current_user': g.get('user'), 'csrf_token': auth.csrf_token,
                'now_timestamp': now_timestamp}

    @app.errorhandler(DomainError)
    def domain_error(error):
        return render_template('error.html', status=error.status, message=error.message), error.status

    @app.errorhandler(HTTPException)
    def http_error(error):
        return render_template('error.html', status=error.code, message=error.description), error.code

    @app.after_request
    def security_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Content-Security-Policy'] = "default-src 'self'; style-src 'self'; script-src 'none'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
        response.headers['Referrer-Policy'] = 'same-origin'
        if g.get('user') or response.mimetype == 'text/html':
            response.headers['Cache-Control'] = 'no-store'
        return response

    return app
