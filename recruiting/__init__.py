"""Application factory for Matchwork."""
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
    from flask import g
    from werkzeug.exceptions import HTTPException
    from . import api, auth, pages, seed
    from .errors import DomainError
    app.register_blueprint(auth.bp)
    app.register_blueprint(api.bp)
    app.register_blueprint(pages.bp)
    app.before_request(auth.load_user)
    seed.init_app(app)

    @app.errorhandler(DomainError)
    def domain_error(error):
        payload = {'ok': False, 'message': error.message}
        if error.errors:
            payload['errors'] = error.errors
        return payload, error.status

    @app.errorhandler(HTTPException)
    def http_error(error):
        return {'ok': False, 'message': error.description}, error.code

    @app.after_request
    def security_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; img-src 'self' data:; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "script-src 'self' 'unsafe-inline'; connect-src 'self'; "
            "object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
        )
        response.headers['Referrer-Policy'] = 'same-origin'
        if g.get('user') or response.mimetype == 'text/html':
            response.headers['Cache-Control'] = 'no-store'
        return response

    return app
