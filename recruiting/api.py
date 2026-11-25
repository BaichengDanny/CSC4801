"""JSON API used by the Matchwork pages. Services still enforce every rule."""
from functools import wraps

from flask import Blueprint, g, request

from . import accounts, jobs, present, scheduling
from .auth import csrf_token, end_session, start_session
from .db import get_db
from .errors import DomainError

bp = Blueprint('api', __name__, url_prefix='/api')


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
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise DomainError(400, 'Send a JSON object.')
    return data


def record_id(value):
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise DomainError(404, 'That record was not found.') from None
    if not 0 < number < 2**63:
        raise DomainError(404, 'That record was not found.')
    return number


def description_from(data):
    full = str(data['body']).strip() if data.get('body') is not None else ''
    summary = str(data['desc']).strip() if data.get('desc') is not None else ''
    return full or summary


def listing_fields(data):
    fields = {'desc': 'summary', 'location': 'location', 'type': 'job_type', 'status': 'posting_status'}
    return {column: data[key] for key, column in fields.items() if key in data}


def employer_slots(actor):
    return get_db().execute(
        'SELECT s.*, j.employer_id, j.title, c.name AS company_name, b.application_id '
        'FROM slots s JOIN jobs j ON j.id = s.job_id '
        'JOIN companies c ON c.employer_id = j.employer_id '
        'LEFT JOIN bookings b ON b.slot_id = s.id WHERE j.employer_id = ? ORDER BY s.starts_at, s.id',
        (actor['id'],)).fetchall()


def candidate_slots(actor):
    return get_db().execute(
        'SELECT s.*, j.employer_id, c.name AS company_name, b.application_id '
        'FROM slots s JOIN jobs j ON j.id = s.job_id '
        'JOIN companies c ON c.employer_id = j.employer_id '
        'LEFT JOIN bookings b ON b.slot_id = s.id '
        'LEFT JOIN applications a ON a.id = b.application_id '
        'WHERE a.candidate_id = ? OR (b.id IS NULL AND s.starts_at > ? AND EXISTS ('
        'SELECT 1 FROM applications eligible JOIN jobs applied_job ON applied_job.id = eligible.job_id '
        'LEFT JOIN bookings existing ON existing.application_id = eligible.id '
        "WHERE eligible.candidate_id = ? AND eligible.status = 'Interviewing' "
        'AND applied_job.employer_id = j.employer_id AND existing.id IS NULL)) '
        'ORDER BY s.starts_at, s.id',
        (actor['id'], scheduling.now_timestamp(), actor['id'])).fetchall()


@bp.get('/auth/csrf')
def get_csrf():
    return {'ok': True, 'csrfToken': csrf_token()}, 200, {'Cache-Control': 'no-store'}


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
    return {'ok': True, 'id': g.user['id'], 'email': g.user['email'], 'role': g.user['role'],
            'name': g.user['display_name'], 'csrfToken': csrf_token()}


@bp.get('/candidate/bootstrap')
@as_role('Candidate')
def candidate_bootstrap():
    details = accounts.profile(g.user, g.user['id'])
    postings = jobs.recommendations(g.user)
    company_rows = {row['employer_id']: row for row in get_db().execute('SELECT * FROM companies')}
    companies = {}
    cards = []
    for posting in postings:
        card = present.job_card(posting)
        cards.append(card)
        if card['owner'] not in companies:
            companies[card['owner']] = present.company_card(company_rows[posting['employer_id']])
    applications = [present.candidate_application(item) for item in jobs.applications(g.user)]
    slots = [present.slot_card(row, row['company_name'], str(row['application_id']) if row['application_id'] else None)
             for row in candidate_slots(g.user)]
    return {
        'ok': True,
        'now': present.iso(None),
        'companies': companies,
        'jobs': cards,
        'state': {
            'v': 2,
            'profile': present.candidate_profile(g.user, details),
            'saved': {},
            'applications': applications,
            'slots': slots,
            'notifRead': False,
        },
    }


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
        data.get('resume', accounts.UNCHANGED),
        headline=data.get('headline', current['headline']),
        location=data.get('location', current['location']),
    )
    return {'ok': True, 'profile': present.candidate_profile(g.user, updated)}


@bp.route('/candidate/<int:candidate_id>/resume', methods=['GET', 'POST'])
@as_role('Candidate')
def candidate_resume(candidate_id):
    accounts.require_owner(g.user, candidate_id)
    if request.method == 'POST':
        resume = accounts.replace_resume(g.user, body().get('resume'))
    else:
        resume = accounts.profile(g.user, candidate_id)['resume']
    return {'ok': True, 'resume': resume}


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


@bp.get('/employer/bootstrap')
@as_role('Employer')
def employer_bootstrap():
    company = accounts.company(g.user)
    postings = [present.job_card(item) for item in jobs.owned_jobs(g.user)]
    applications = []
    people = {}
    for posting in jobs.owned_jobs(g.user):
        for applicant in jobs.applicants(g.user, posting['id']):
            applications.append(present.employer_application(applicant))
            people[applicant['candidate_id']] = applicant
    candidates = []
    for applicant in people.values():
        profile = get_db().execute(
            'SELECT u.id AS candidate_id, u.display_name, u.email, p.headline, p.location '
            'FROM users u JOIN candidate_profiles p ON p.user_id = u.id WHERE u.id = ?',
            (applicant['candidate_id'],)).fetchone()
        candidates.append(present.person(profile, applicant['skills']))
    slots = [present.slot_card(row, row['company_name'], str(row['application_id']) if row['application_id'] else None)
             for row in employer_slots(g.user)]
    return {
        'ok': True,
        'now': present.iso(None),
        'me': str(g.user['id']),
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


@bp.post('/employer/jobs')
@as_role('Employer')
def create_job():
    data = body()
    created = jobs.create_job(g.user, data.get('title', ''), description_from(data),
                              data.get('skills', []), listing=listing_fields(data))
    return {'ok': True, 'job': present.job_card(created)}, 201


@bp.post('/employer/jobs/<int:job_id>')
@as_role('Employer')
def update_job(job_id):
    data = body()
    changes = {key: data[key] for key in ('title', 'skills') if key in data}
    description = description_from(data)
    if description or data.get('desc') is not None:
        changes['description'] = description
    saved = jobs.update_job(g.user, job_id, listing=listing_fields(data), **changes)
    return {'ok': True, 'job': present.job_card(saved)}


@bp.post('/employer/jobs/<int:job_id>/delete')
@as_role('Employer')
def delete_job(job_id):
    jobs.delete_job(g.user, job_id)
    return {'ok': True}


@bp.post('/employer/applications/<int:application_id>/status')
@as_role('Employer')
def set_status(application_id):
    data = body()
    updated = jobs.set_status(g.user, application_id, data.get('status', ''))
    return {'ok': True, 'application': present.employer_application(updated)}


@bp.post('/employer/slots')
@as_role('Employer')
def create_slot():
    data = body()
    created = scheduling.create_slot(g.user, None, data.get('start'), data.get('end'))
    return {'ok': True, 'slot': present.slot_card(created, created['company_name'], None)}, 201


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
