"""Synthetic, repeatable demo data; no real identities or credentials."""
import secrets
from datetime import datetime, timedelta, timezone

import click

from . import accounts, jobs, scheduling
from .db import migrate, transaction


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
