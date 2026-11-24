"""Account creation, authentication, and role-specific profile services."""
import re
import sqlite3

from werkzeug.security import check_password_hash, generate_password_hash

from .db import get_db, transaction
from .errors import DomainError
from .matching import normalize_skills


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
        'SELECT resume, headline, location FROM candidate_profiles WHERE user_id = ?', (candidate_id,)).fetchone()
    if row is None:
        raise DomainError(404, 'Candidate profile not found.')
    return {**user(candidate_id), 'resume': row['resume'], 'headline': row['headline'],
            'location': row['location'], 'skills': skills_for(candidate_id)}


def update_profile(actor, display_name, skills, resume, headline=None, location=None):
    require_role(actor, 'Candidate')
    name = text_value(display_name, 'Display name', 100)
    normalized = normalize_skills(skills)
    resume = text_value(resume, 'Resume', 50000, required=False)
    current = get_db().execute(
        'SELECT headline, location FROM candidate_profiles WHERE user_id = ?', (actor['id'],)).fetchone()
    headline = current['headline'] if headline is None else text_value(headline, 'Headline', 160, required=False).strip()
    location = current['location'] if location is None else text_value(location, 'Location', 120, required=False).strip()
    with transaction() as db:
        db.execute('UPDATE users SET display_name = ? WHERE id = ?', (name, actor['id']))
        db.execute('UPDATE candidate_profiles SET resume = ?, headline = ?, location = ? WHERE user_id = ?',
                   (resume, headline, location, actor['id']))
        db.execute('DELETE FROM candidate_skills WHERE candidate_id = ?', (actor['id'],))
        db.executemany('INSERT INTO candidate_skills VALUES (?,?)', [(actor['id'], s) for s in normalized])
    return profile(actor, actor['id'])


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
