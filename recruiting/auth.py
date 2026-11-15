"""Revocable server sessions and browser request protection."""
import hashlib
import hmac
import secrets
from functools import wraps

from flask import Blueprint, g, redirect, render_template, request, session, url_for

from . import accounts
from .db import get_db, transaction
from .errors import DomainError
from .scheduling import now_timestamp

bp = Blueprint('auth', __name__)


def csrf_token():
    if 'csrf_token' not in session:
        session['csrf_token'] = secrets.token_urlsafe(32)
    return session['csrf_token']


def _digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def generation():
    return get_db().execute("SELECT value FROM metadata WHERE key = 'session_generation'").fetchone()[0]


def load_user():
    g.user = None
    token = session.get('auth_token')
    if token:
        row = get_db().execute('SELECT user_id FROM auth_sessions WHERE token_hash = ? AND expires_at > ?',
                               (_digest(token), now_timestamp())).fetchone()
        if row and session.get('generation') == generation():
            g.user = accounts.user(row['user_id'])
        else:
            session.clear()
    if request.method == 'POST':
        if request.endpoint not in ('auth.login', 'auth.register') and g.user is None:
            raise DomainError(401, 'Please sign in to continue.')
        expected, supplied = session.get('csrf_token'), request.form.get('csrf_token')
        if not expected or not supplied or not hmac.compare_digest(expected.encode('utf-8'), supplied.encode('utf-8')):
            raise DomainError(400, 'Your form expired. Reload the page and try again.')


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            raise DomainError(401, 'Please sign in to continue.')
        return view(*args, **kwargs)
    return wrapped


def start_session(actor):
    old_token = session.get('auth_token')
    token = secrets.token_urlsafe(32)
    with transaction() as db:
        if old_token:
            db.execute('DELETE FROM auth_sessions WHERE token_hash = ?', (_digest(old_token),))
        db.execute('DELETE FROM auth_sessions WHERE expires_at <= ?', (now_timestamp(),))
        db.execute('INSERT INTO auth_sessions VALUES (?,?,?)',
                   (_digest(token), actor['id'], int(now_timestamp()) + 43200))
    session.clear()
    session.update(auth_token=token, generation=generation())
    csrf_token()


@bp.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        try:
            actor = accounts.authenticate(request.form.get('email', ''), request.form.get('password', ''))
            start_session(actor)
            return redirect(url_for('web.dashboard'))
        except DomainError as exc:
            error = exc
    return render_template('auth.html', registering=False, error=error), error.status if error else 200


@bp.route('/register', methods=['GET', 'POST'])
def register():
    error = None
    if request.method == 'POST':
        try:
            actor = accounts.register(request.form.get('email', ''), request.form.get('password', ''),
                                      request.form.get('role', ''), request.form.get('display_name', ''))
            start_session(actor)
            return redirect(url_for('web.dashboard'))
        except DomainError as exc:
            error = exc
    return render_template('auth.html', registering=True, error=error), error.status if error else 200


@bp.post('/logout')
@login_required
def logout():
    with transaction() as db:
        db.execute('DELETE FROM auth_sessions WHERE token_hash = ?', (_digest(session['auth_token']),))
    session.clear()
    return redirect(url_for('auth.login'))
