"""JSON API used by the Matchwork pages. Services still enforce every rule."""
from datetime import datetime, timezone
from functools import wraps

from flask import Blueprint, g, request

from . import accounts, jobs, present, scheduling
from .auth import end_session, start_session
from .db import get_db, transaction
from .errors import DomainError
from .matching import normalize_skills, score

bp = Blueprint('api', __name__, url_prefix='/api')
JOB_TYPES = ('Full-time', 'Part-time', 'Contract', 'Internship')


def as_role(role):
    def decorate(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            accounts.require_role(g.user, role)
            return view(*args, **kwargs)
        return wrapped
    return decorate


def body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise DomainError(400, 'Send a JSON object.')
    return data


def record_id(value):
    # JSON booleans/floats must never select a different integer record.
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise DomainError(404, 'That record was not found.')
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise DomainError(404, 'That record was not found.') from None
    if not 0 < number < 2**63:
        raise DomainError(404, 'That record was not found.')
    return number


def description_from(data, current=''):
    summary = data.get('desc', None)
    full = data.get('body', None)
    if summary is None and full is None:
        return current
    summary = current if summary is None else str(summary)
    full = '' if full is None else str(full)
    text = full.strip() or summary.strip()
    return text


def save_listing(actor, posting, data):
    summary = str(data.get('desc', posting['summary']) or '')
    location = str(data.get('location', posting['location']) or '')
    job_type = str(data.get('type', posting['job_type']) or 'Full-time')
    status = str(data.get('status', posting['posting_status']) or 'Active')
    if status not in ('Active', 'Closed'):
        raise DomainError(400, 'Choose Active or Closed.')
    if job_type not in JOB_TYPES:
        raise DomainError(400, 'Choose a job type.')
    accounts.text_value(summary, 'Job summary', 300, required=False)
    accounts.text_value(location, 'Location', 120, required=False)
    with transaction():
        jobs.job(actor, posting['id'])
        get_db().execute(
            'UPDATE jobs SET summary = ?, location = ?, job_type = ?, posting_status = ? WHERE id = ?',
            (summary.strip(), location.strip(), job_type, status, posting['id']))
    return jobs.job(actor, posting['id'])


def employer_slots(actor):
    return get_db().execute(
        'SELECT s.*, j.employer_id, j.title, c.name AS company_name, b.application_id '
        'FROM slots s JOIN jobs j ON j.id = s.job_id '
        'JOIN companies c ON c.employer_id = j.employer_id '
        'LEFT JOIN bookings b ON b.slot_id = s.id WHERE j.employer_id = ? ORDER BY s.starts_at, s.id',
        (actor['id'],)).fetchall()


def candidate_slots():
    return get_db().execute(
        'SELECT s.*, j.employer_id, c.name AS company_name, b.application_id, a.candidate_id AS booked_candidate '
        'FROM slots s JOIN jobs j ON j.id = s.job_id '
        'JOIN companies c ON c.employer_id = j.employer_id '
        'LEFT JOIN bookings b ON b.slot_id = s.id '
        'LEFT JOIN applications a ON a.id = b.application_id ORDER BY s.starts_at, s.id').fetchall()


def slot_for_viewer(row, viewer_id):
    booked = row['application_id']
    if booked is None:
        marker = None
    elif row['booked_candidate'] == viewer_id:
        marker = str(booked)
    else:
        marker = 'other'
    return present.slot_card(row, row['company_name'], marker)


@bp.post('/auth/register')
def register():
    data = body()
    role = data.get('role')
    if role not in ('Candidate', 'Employer'):
        raise DomainError(400, 'Choose Candidate or Employer.')
    company_name = None
    if role == 'Employer' and str(data.get('company') or '').strip():
        company_name = accounts.text_value(str(data.get('company')), 'Company name', 100)
    actor = accounts.register(data.get('email', ''), data.get('password', ''), role, data.get('name', ''))
    if company_name:
        accounts.update_company(actor, company_name, '')
    start_session(actor)
    return {'ok': True, 'role': actor['role'], 'name': actor['display_name']}, 201


@bp.post('/auth/login')
def login():
    data = body()
    role = data.get('role')
    if role not in ('Candidate', 'Employer'):
        raise DomainError(400, 'Choose Candidate or Employer.')
    actor = accounts.authenticate(data.get('email', ''), data.get('password', ''))
    if actor['role'] != role:
        raise DomainError(403, f'This account is registered as a {actor["role"]}. Switch tabs and sign in again.')
    start_session(actor)
    return {'ok': True, 'role': actor['role'], 'name': actor['display_name']}


@bp.post('/auth/logout')
def logout():
    if g.user is None:
        raise DomainError(401, 'Please sign in to continue.')
    end_session()
    return {'ok': True}


@bp.get('/auth/me')
def me():
    if g.user is None:
        raise DomainError(401, 'Please sign in to continue.')
    return {'ok': True, 'id': g.user['id'], 'email': g.user['email'], 'role': g.user['role'], 'name': g.user['display_name']}


def _candidate_payload(actor):
    details = accounts.profile(actor, actor['id'])
    postings = jobs.recommendations(actor)
    company_rows = {row['employer_id']: row for row in get_db().execute('SELECT * FROM companies')}
    companies = {}
    cards = []
    for rank, posting in enumerate(postings):
        card = present.job_card({**posting, 'rank': rank})
        cards.append(card)
        record = company_rows.get(posting['employer_id'])
        companies.setdefault(
            str(posting['employer_id']),
            present.company_card(record) if record else {'name': posting['company_name'], **present.paint(posting['company_name'])})
    applications = [present.candidate_application(item) for item in jobs.applications(actor)]
    slots = [slot_for_viewer(row, actor['id']) for row in candidate_slots()]
    return {
        'ok': True,
        'now': present.iso(None),
        'companies': companies,
        'jobs': cards,
        'state': {
            'v': 2,
            'profile': present.candidate_profile(actor, details),
            'saved': {},
            'applications': applications,
            'slots': slots,
            'notifRead': False,
        },
    }


@bp.get('/candidate/bootstrap')
@as_role('Candidate')
def candidate_bootstrap():
    return _candidate_payload(g.user)


@bp.post('/candidate/matching-preview')
@as_role('Candidate')
def candidate_matching_preview():
    # Read-only draft scoring: the same normalization, formula and ordering.
    skills = normalize_skills(body().get('skills'))
    rows = jobs.recommendations(g.user, skills=skills)
    saved_skills = accounts.skills_for(g.user['id'])
    return {'ok': True, 'jobs': [
        {**present.job_card({**row, 'rank': rank}), 'baselineScore': score(saved_skills, row['skills'])}
        for rank, row in enumerate(rows)]}


@bp.post('/candidate/profile')
@as_role('Candidate')
def update_candidate_profile():
    data = body()
    current = accounts.profile(g.user, g.user['id'])
    skills = data.get('skills', current['skills'])
    updated = accounts.update_profile(
        g.user,
        data.get('name', current['display_name']),
        skills,
        data.get('resume', current['resume']),
        headline=data.get('headline', current['headline']),
        location=data.get('location', current['location']),
    )
    return {'ok': True, 'profile': present.candidate_profile(g.user, updated),
            'snapshot': _candidate_payload(g.user)}


@bp.post('/candidate/applications')
@as_role('Candidate')
def apply():
    data = body()
    created = jobs.apply(g.user, record_id(data.get('jobId')))
    return {'ok': True, 'application': present.candidate_application(created)}, 201


@bp.post('/candidate/applications/<int:application_id>/book')
@as_role('Candidate')
def book(application_id):
    jobs.application(g.user, application_id)
    data = body()
    scheduling.book(g.user, application_id, record_id(data.get('slotId')))
    return {'ok': True, 'application': present.candidate_application(jobs.application(g.user, application_id))}


def _employer_payload(actor):
    company = accounts.company(actor)
    postings = [present.job_card(item, actor['id']) for item in jobs.owned_jobs(actor)]
    applications = []
    people = {}
    for rank, applicant in enumerate(jobs.ranked_applications(actor)):
        applications.append(present.employer_application({**applicant, 'rank': rank}))
        people[applicant['candidate_id']] = applicant
    candidates = []
    for applicant in people.values():
        profile = get_db().execute(
            'SELECT u.id AS candidate_id, u.display_name, u.email, p.headline, p.location '
            'FROM users u JOIN candidate_profiles p ON p.user_id = u.id WHERE u.id = ?',
            (applicant['candidate_id'],)).fetchone()
        candidates.append(present.person(profile, applicant['skills']))
    slots = [present.slot_card(row, row['company_name'], str(row['application_id']) if row['application_id'] else None)
             for row in employer_slots(actor)]
    return {
        'ok': True,
        'now': present.iso(None),
        'me': str(actor['id']),
        'state': {
            'v': 1,
            'company': present.company_card(company),
            'candidates': candidates,
            'jobs': postings,
            'applications': applications,
            'slots': slots,
            'notifRead': False,
            'clock': 0,
        },
    }


@bp.get('/employer/bootstrap')
@as_role('Employer')
def employer_bootstrap():
    return _employer_payload(g.user)


@bp.post('/employer/jobs')
@as_role('Employer')
def create_job():
    data = body()
    # Core fields and page metadata form one request-level write.
    with transaction():
        created = jobs.create_job(g.user, data.get('title', ''), description_from(data), data.get('skills', []))
        saved = save_listing(g.user, created, data)
    return {'ok': True, 'job': present.job_card(saved, g.user['id']),
            'snapshot': _employer_payload(g.user)}, 201


@bp.post('/employer/jobs/<int:job_id>')
@as_role('Employer')
def update_job(job_id):
    data = body()
    with transaction():
        current = jobs.job(g.user, job_id)
        if any(key in data for key in ('title', 'body', 'desc', 'skills')):
            current = jobs.update_job(
                g.user, job_id,
                data.get('title', current['title']),
                description_from(data, current['description']),
                data.get('skills', current['skills']))
        saved = save_listing(g.user, current, data)
    return {'ok': True, 'job': present.job_card(saved, g.user['id']),
            'snapshot': _employer_payload(g.user)}


@bp.post('/employer/jobs/<int:job_id>/delete')
@as_role('Employer')
def delete_job(job_id):
    jobs.delete_job(g.user, job_id)
    return {'ok': True, 'snapshot': _employer_payload(g.user)}


@bp.post('/employer/applications/<int:application_id>/status')
@as_role('Employer')
def set_status(application_id):
    data = body()
    updated = jobs.set_status(g.user, application_id, data.get('status', ''))
    snapshot = _employer_payload(g.user)
    card = next(item for item in snapshot['state']['applications'] if item['id'] == str(updated['id']))
    return {'ok': True, 'application': card, 'snapshot': snapshot}


@bp.post('/employer/slots')
@as_role('Employer')
def create_slot():
    data = body()
    start, end = normalize_slot(data.get('start'), data.get('end'))
    anchor = get_db().execute('SELECT id FROM jobs WHERE employer_id = ? ORDER BY id LIMIT 1', (g.user['id'],)).fetchone()
    if anchor is None:
        raise DomainError(400, 'Create a job before adding interview times.')
    start_time, end_time = scheduling.parse_time(start), scheduling.parse_time(end)
    if end_time - start_time != 1800:
        raise DomainError(400, 'Interview slots must last exactly 30 minutes.')
    if overlapping_slot(g.user['id'], start_time, end_time) is not None:
        raise DomainError(409, 'That overlaps another interview time.')
    created = scheduling.create_slot(g.user, anchor['id'], start, end)
    row = get_db().execute(
        'SELECT s.*, j.employer_id, c.name AS company_name, b.application_id FROM slots s '
        'JOIN jobs j ON j.id = s.job_id JOIN companies c ON c.employer_id = j.employer_id '
        'LEFT JOIN bookings b ON b.slot_id = s.id WHERE s.id = ?', (created['id'],)).fetchone()
    return {'ok': True, 'slot': present.slot_card(row, row['company_name'], None)}, 201


@bp.post('/employer/slots/<int:slot_id>/delete')
@as_role('Employer')
def delete_slot(slot_id):
    scheduling.delete_slot(g.user, slot_id)
    return {'ok': True}


@bp.post('/employer/company')
@as_role('Employer')
def update_company():
    data = body()
    current = accounts.company(g.user)
    updated = accounts.update_company(
        g.user,
        data.get('name', current['name']),
        data.get('about', current['description']),
        industry=data.get('industry', current['industry']),
        size=data.get('size', current['size']),
        location=data.get('location', current['location']),
        website=data.get('website', current['website']),
    )
    return {'ok': True, 'company': present.company_card(updated)}


def normalize_slot(start, end):
    try:
        parsed = [
            datetime.fromtimestamp(scheduling.parse_time(value), timezone.utc).isoformat()
            for value in (start, end)
        ]
    except (OSError, OverflowError, ValueError) as error:
        raise DomainError(400, 'Enter a valid start and end time.') from error
    return parsed[0], parsed[1]


def overlapping_slot(employer_id, start, end):
    for row in get_db().execute(
            'SELECT s.starts_at, s.ends_at FROM slots s JOIN jobs j ON j.id = s.job_id WHERE j.employer_id = ?',
            (employer_id,)):
        if row['starts_at'] < end and row['ends_at'] > start:
            return row
    return None
