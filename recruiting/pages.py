"""Serve the Matchwork pages. Authorization stays in the JSON API and services."""
from pathlib import Path

from flask import Blueprint, abort, g, redirect, send_from_directory

bp = Blueprint('ui', __name__)
ROOT = Path(__file__).resolve().parent.parent


@bp.get('/')
def index():
    if g.user is None:
        return redirect('/sign-in')
    return redirect('/candidate/dashboard' if g.user['role'] == 'Candidate' else '/recruiter/dashboard')


@bp.get('/health')
def health():
    return {'status': 'ok'}


def send_ui(base, filename):
    base = base.resolve()
    relative = Path(filename)
    if relative.suffix == '':
        relative = relative.with_suffix('.html')
    target = (base / relative).resolve()
    if base not in target.parents or not target.is_file():
        abort(404)
    return send_from_directory(target.parent, target.name)


@bp.get('/sign-in')
def sign_in():
    return send_from_directory(ROOT, 'login.html')


@bp.get('/candidate/')
@bp.get('/candidate/<path:filename>')
def candidate(filename='dashboard'):
    return send_ui(ROOT / 'candidate', filename)


@bp.get('/recruiter/')
@bp.get('/recruiter/<path:filename>')
def recruiter(filename='dashboard'):
    return send_ui(ROOT / 'recruiter', filename)


@bp.get('/shared/<path:filename>')
def shared(filename):
    return send_ui(ROOT / 'shared', filename)
