"""Synthetic, repeatable demo data; no real identities or credentials."""
import json
import re
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

import click

from . import accounts, jobs, scheduling
from .db import migrate, transaction

CATALOG = Path(__file__).resolve().parents[1] / 'candidate' / 'assets' / 'jobs.json'


def seed_demo(at):
    if at.tzinfo is None:
        raise ValueError('Seed reference time must include a timezone.')
    migrate()
    with transaction() as db:
        # Fixed table names, in foreign-key dependency order.
        for table in ('auth_sessions', 'bookings', 'slots', 'applications', 'job_skills',
                      'jobs', 'candidate_skills', 'candidate_profiles', 'companies', 'users'):
            db.execute(f'DELETE FROM {table}')
        db.execute("UPDATE metadata SET value = ? WHERE key = 'session_generation'", (secrets.token_hex(24),))
    password = 'DemoPass123!'  # Public, local/demo-only credentials.
    alex = accounts.register('alex@example.test', password, 'Candidate', 'Alex Morgan')
    blair = accounts.register('blair@example.test', password, 'Candidate', 'Blair Chen')
    casey = accounts.register('casey@example.test', password, 'Candidate', 'Casey Rivers')
    north = accounts.register('north@example.test', password, 'Employer', 'Taylor Lee')
    field = accounts.register('field@example.test', password, 'Employer', 'Sam Rivera')
    accounts.update_profile(alex, 'Alex Morgan', ['Python', 'SQL'], 'Demo resume: I enjoy building reliable software and working with data.')
    accounts.update_profile(blair, 'Blair Chen', ['Python'], 'Demo resume: Python developer interested in thoughtful products.')
    accounts.update_profile(casey, 'Casey Rivers', ['Rust'], 'Demo resume: Systems programmer focused on performance.')
    accounts.update_company(north, 'Northstar Studio', 'A small engineering team building useful, dependable software. We value curiosity, ownership, and clear communication.')
    accounts.update_company(field, 'Fieldwork Labs', 'We make practical tools that help people do their best work. Join a collaborative team with room to grow.')
    backend = jobs.create_job(north, 'Backend Engineer', 'Build the services behind everyday products.\n\nYou will design clear APIs, work with relational data, and help us ship reliable features. We are looking for someone who enjoys solving problems with a small, collaborative team.', ['Python', 'SQL'])
    data = jobs.create_job(north, 'Data Analyst', 'Turn thoughtful questions into useful insights. Work with the product team to explore data, write clear queries, and communicate what you find.', ['SQL', 'Python', 'Statistics'])
    systems = jobs.create_job(field, 'Systems Engineer', 'Help build fast, dependable tools in Rust. You will work on performance, testing, and the small details that make software feel great.', ['Rust', 'Linux'])
    graduate = jobs.create_job(field, 'Graduate Programme', 'Start your career with hands-on projects and supportive mentorship. Bring your curiosity; we will help you discover the work you love.', [])
    for c in (alex, blair):
        a = jobs.apply(c, backend['id'])
        jobs.set_status(north, a['id'], 'Interviewing')
    jobs.apply(alex, data['id'])
    rejected = jobs.apply(blair, systems['id'])
    jobs.set_status(field, rejected['id'], 'Rejected')
    accepted = jobs.apply(casey, graduate['id'])
    jobs.set_status(field, accepted['id'], 'Accepted')
    day = at.astimezone(timezone.utc).replace(hour=10, minute=0, second=0, microsecond=0) + timedelta(days=1)
    # Use the reference clock during seeding so a fixed --at reproduces old fixtures.
    from flask import current_app
    original_clock = current_app.config['NOW']
    current_app.config['NOW'] = lambda: at
    try:
        for offset in (0, 1, 2):
            start = day + timedelta(hours=offset)
            scheduling.create_slot(north, backend['id'], start.isoformat(), (start + timedelta(minutes=30)).isoformat())
        scheduling.create_slot(field, systems['id'], day.isoformat(), (day + timedelta(minutes=30)).isoformat())
    finally:
        current_app.config['NOW'] = original_clock
    _seed_catalog(password)


def _catalog_email(name):
    slug = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')
    return f'{slug}@example.test'


def _display_skills(values):
    seen = set()
    kept = []
    for value in values:
        text = str(value).strip()
        key = text.lower()
        if text and key not in seen:
            seen.add(key)
            kept.append(text)
    return kept


def _seed_catalog(password):
    """Load the Matchwork job catalog. Each company is its own demo employer."""
    catalog = json.loads(CATALOG.read_text())
    employers = {}
    for name, company in catalog['companies'].items():
        actor = accounts.register(_catalog_email(name), password, 'Employer', name)
        accounts.update_company(
            actor, name, company.get('about') or name,
            industry=company.get('industry') or '', size=company.get('size') or '',
            location=company.get('location') or '', website=company.get('website') or '')
        with transaction() as db:
            db.execute(
                'UPDATE companies SET logo = ?, logo_w = ?, logo_h = ? WHERE employer_id = ?',
                (company.get('logo') or '', int(company.get('w') or 0), int(company.get('h') or 0), actor['id']))
        employers[name] = actor
    for posting in catalog['jobs']:
        created = jobs.create_job(employers[posting['company']], posting['title'], posting['body'], posting['skills'])
        posted = datetime.fromisoformat(posting['posted']).replace(hour=12, tzinfo=timezone.utc)
        with transaction() as db:
            db.execute(
                'UPDATE jobs SET summary = ?, location = ?, job_type = ?, created_at = ?, '
                'logo = ?, logo_w = ?, logo_h = ?, categories = ? WHERE id = ?',
                (posting['desc'].strip(), (posting.get('location') or '').strip(), posting.get('type') or 'Full-time',
                 int(posted.timestamp()), posting.get('logo') or '', int(posting.get('w') or 0),
                 int(posting.get('h') or 0), json.dumps(posting.get('cats') or []), created['id']))
            db.execute('DELETE FROM job_skills WHERE job_id = ?', (created['id'],))
            db.executemany(
                'INSERT INTO job_skills VALUES (?,?)',
                [(created['id'], skill) for skill in _display_skills(posting['skills'])])


def init_app(app):
    @app.cli.command('seed')
    @click.option('--yes', is_flag=True, help='Confirm resetting all data in the configured local database.')
    @click.option('--at', default=None, help='ISO reference time including timezone; default is now (UTC).')
    def seed_command(yes, at):
        """Reset the local database and create synthetic demonstration data."""
        if not yes:
            raise click.UsageError('This resets all local data. Supply --yes to confirm.')
        try:
            reference = datetime.fromisoformat(at) if at else app.config['NOW']()
            if reference.tzinfo is None:
                raise ValueError
        except ValueError as error:
            raise click.BadParameter('Use an ISO timestamp with a timezone.', param_hint='--at') from error
        seed_demo(reference)
        click.echo('Local demo data reset and seeded. Demo password: DemoPass123!')
