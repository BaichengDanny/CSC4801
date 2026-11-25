"""Account creation, authentication, and role-specific profile services."""
import re
import sqlite3

from flask import current_app
from werkzeug.security import check_password_hash, generate_password_hash

from .db import get_db, transaction
from .errors import DomainError
from .matching import normalize_skills


RESUME_LIMIT = 50_000
UNCHANGED = object()
PREFERRED_JOB_TYPES = ('Full-time', 'Contract', 'Any')


def _now():
    return int(current_app.config['NOW']().timestamp())


def require_role(actor, role):
    if actor is None:
        raise DomainError(401, 'Please sign in to continue.')
    if actor['role'] != role:
        raise DomainError(403, 'You do not have permission to do that.')


def require_owner(actor, owner_id):
    if actor['id'] != owner_id:
        raise DomainError(403, 'You do not have permission to access this record.')


def text_value(value, label, limit, required=True):
    if isinstance(value, str) and '\x00' in value:
        raise DomainError(400, f'{label} contains an unsupported character.')
    if not isinstance(value, str) or (required and not value.strip()) or len(value) > limit:
        raise DomainError(400, f'{label} must be {"non-empty and " if required else ""}at most {limit} characters.')
    return value.strip() if required else value


def user(user_id):
    row = get_db().execute('SELECT id, email, role, display_name FROM users WHERE id = ?', (user_id,)).fetchone()
    return dict(row) if row else None


def register(email, password, role, display_name):
    email = text_value(email, 'Email', 254).lower()
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email):
        raise DomainError(400, 'Enter a valid email address.')
    if not isinstance(password, str) or not 8 <= len(password) <= 256:
        raise DomainError(400, 'Password must contain 8 to 256 characters.')
    if role not in ('Candidate', 'Employer'):
        raise DomainError(400, 'Choose Candidate or Employer.')
    name = text_value(display_name, 'Display name', 100)
    password_hash = generate_password_hash(password, method='scrypt')
    try:
        with transaction() as db:
            cursor = db.execute('INSERT INTO users(email,password_hash,role,display_name) VALUES (?,?,?,?)',
                                (email, password_hash, role, name))
            user_id = cursor.lastrowid
            if role == 'Candidate':
                db.execute('INSERT INTO candidate_profiles(user_id) VALUES (?)', (user_id,))
            else:
                db.execute('INSERT INTO companies(employer_id,name) VALUES (?,?)', (user_id, name))
    except sqlite3.IntegrityError as error:
        if get_db().execute('SELECT 1 FROM users WHERE email = ?', (email,)).fetchone():
            raise DomainError(409, 'An account with this email already exists.') from error
        raise
    return user(user_id)


def authenticate(email, password):
    if not isinstance(email, str) or not isinstance(password, str) or len(password) > 256:
        raise DomainError(401, 'Email or password is incorrect.')
    row = get_db().execute('SELECT id, password_hash FROM users WHERE email = ?', (email.strip().lower(),)).fetchone()
    if row is None or not check_password_hash(row['password_hash'], password):
        raise DomainError(401, 'Email or password is incorrect.')
    return user(row['id'])


def skills_for(candidate_id):
    return [r['skill'] for r in get_db().execute(
        'SELECT skill FROM candidate_skills WHERE candidate_id = ? ORDER BY skill', (candidate_id,))]


def profile(actor, candidate_id):
    require_role(actor, 'Candidate')
    require_owner(actor, candidate_id)
    row = get_db().execute(
        'SELECT resume, headline, location, resume_updated_at, pref_job_type, pref_remote '
        'FROM candidate_profiles WHERE user_id = ?', (candidate_id,)).fetchone()
    if row is None:
        raise DomainError(404, 'Candidate profile not found.')
    prefs = {'type': row['pref_job_type'], 'remote': bool(row['pref_remote'])} if row['pref_job_type'] else None
    return {**user(candidate_id), 'resume': row['resume'], 'headline': row['headline'],
            'location': row['location'], 'skills': skills_for(candidate_id),
            'resume_updated_at': row['resume_updated_at'], 'prefs': prefs}


def preference_values(prefs):
    """Validate the profile form's work preferences: a job type and an open-to-remote flag."""
    if (not isinstance(prefs, dict) or prefs.get('type') not in PREFERRED_JOB_TYPES
            or not isinstance(prefs.get('remote'), bool)):
        raise DomainError(400, 'Work preferences need a job type of Full-time, Contract, or Any, and a remote choice.')
    return prefs['type'], int(prefs['remote'])


def update_profile(actor, display_name, skills, resume, headline=None, location=None, prefs=None):
    """Validate every field first, then write them together. None or UNCHANGED keeps a stored value."""
    require_role(actor, 'Candidate')
    name = text_value(display_name, 'Display name', 100)
    normalized = normalize_skills(skills)
    resume = None if resume is UNCHANGED else text_value(resume, 'Resume', RESUME_LIMIT, required=False)
    current = get_db().execute(
        'SELECT headline, location, pref_job_type, pref_remote FROM candidate_profiles WHERE user_id = ?',
        (actor['id'],)).fetchone()
    headline = current['headline'] if headline is None else text_value(headline, 'Headline', 160, required=False).strip()
    location = current['location'] if location is None else text_value(location, 'Location', 120, required=False).strip()
    job_type, remote = ((current['pref_job_type'], current['pref_remote']) if prefs is None
                        else preference_values(prefs))
    with transaction() as db:
        db.execute('UPDATE users SET display_name = ? WHERE id = ?', (name, actor['id']))
        db.execute('UPDATE candidate_profiles SET resume = COALESCE(?, resume), '
                   'resume_updated_at = CASE WHEN ? IS NULL THEN resume_updated_at ELSE ? END, '
                   'headline = ?, location = ?, pref_job_type = ?, pref_remote = ? WHERE user_id = ?',
                   (resume, resume, _now(), headline, location, job_type, remote, actor['id']))
        db.execute('DELETE FROM candidate_skills WHERE candidate_id = ?', (actor['id'],))
        db.executemany('INSERT INTO candidate_skills VALUES (?,?)', [(actor['id'], s) for s in normalized])
    return profile(actor, actor['id'])


def replace_resume(actor, resume):
    require_role(actor, 'Candidate')
    resume = text_value(resume, 'Resume', RESUME_LIMIT, required=False)
    with transaction() as db:
        updated = db.execute('UPDATE candidate_profiles SET resume = ?, resume_updated_at = ? WHERE user_id = ?',
                             (resume, _now(), actor['id']))
        if updated.rowcount == 0:
            raise DomainError(404, 'Candidate profile not found.')
    return resume


def company(actor):
    require_role(actor, 'Employer')
    return dict(get_db().execute('SELECT * FROM companies WHERE employer_id = ?', (actor['id'],)).fetchone())


def update_company(actor, name, description, industry=None, size=None, location=None, website=None):
    require_role(actor, 'Employer')
    name = text_value(name, 'Company name', 100)
    description = text_value(description, 'Company description', 10000, required=False)
    current = company(actor)

    def optional(value, label, limit, fallback):
        if value is None:
            return fallback
        return text_value(value, label, limit, required=False).strip()

    industry = optional(industry, 'Industry', 80, current['industry'])
    size = optional(size, 'Company size', 80, current['size'])
    location = optional(location, 'Location', 120, current['location'])
    website = optional(website, 'Website', 200, current['website'])
    with transaction() as db:
        db.execute(
            'UPDATE companies SET name = ?, description = ?, industry = ?, size = ?, location = ?, website = ? '
            'WHERE employer_id = ?',
            (name, description, industry, size, location, website, actor['id']))
    return company(actor)
