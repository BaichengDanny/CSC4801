"""Job and application workflows with explicit ownership checks."""
from flask import current_app

from .accounts import require_owner, require_role, skills_for, text_value
from .db import get_db, transaction
from .errors import DomainError
from .matching import normalize_skills, score

STATUSES = ('Pending', 'Interviewing', 'Rejected', 'Accepted')


def _job(job_id):
    row = get_db().execute(
        'SELECT j.*, c.name AS company_name, c.description AS company_description '
        'FROM jobs j JOIN companies c ON c.employer_id = j.employer_id WHERE j.id = ?', (job_id,)
    ).fetchone()
    if row is None:
        raise DomainError(404, 'Job not found.')
    result = dict(row)
    result['skills'] = [r['skill'] for r in get_db().execute(
        'SELECT skill FROM job_skills WHERE job_id = ? ORDER BY skill', (job_id,))]
    return result


def job(actor, job_id):
    if actor is None:
        raise DomainError(401, 'Please sign in to continue.')
    if actor['role'] not in ('Candidate', 'Employer'):
        raise DomainError(403, 'You do not have permission to do that.')
    result = _job(job_id)
    if actor['role'] == 'Employer':
        require_owner(actor, result['employer_id'])
    return result


def _job_values(title, description, skills):
    return (text_value(title, 'Job title', 150),
            text_value(description, 'Job description', 10000), normalize_skills(skills))


def create_job(actor, title, description, skills):
    require_role(actor, 'Employer')
    title, description, skills = _job_values(title, description, skills)
    with transaction() as db:
        job_id = db.execute(
            'INSERT INTO jobs(employer_id,title,description,created_at) VALUES (?,?,?,?)',
            (actor['id'], title, description, int(current_app.config['NOW']().timestamp()))).lastrowid
        db.executemany('INSERT INTO job_skills VALUES (?,?)', [(job_id, s) for s in skills])
    return job(actor, job_id)


def update_job(actor, job_id, title, description, skills):
    require_role(actor, 'Employer')
    with transaction() as db:
        job(actor, job_id)
        title, description, skills = _job_values(title, description, skills)
        db.execute('UPDATE jobs SET title = ?, description = ? WHERE id = ?', (title, description, job_id))
        db.execute('DELETE FROM job_skills WHERE job_id = ?', (job_id,))
        db.executemany('INSERT INTO job_skills VALUES (?,?)', [(job_id, s) for s in skills])
    return job(actor, job_id)


def delete_job(actor, job_id):
    require_role(actor, 'Employer')
    with transaction() as db:
        job(actor, job_id)
        if (db.execute('SELECT 1 FROM applications WHERE job_id = ?', (job_id,)).fetchone()
                or db.execute('SELECT 1 FROM slots WHERE job_id = ?', (job_id,)).fetchone()):
            raise DomainError(409, 'Jobs with applications or interview slots cannot be deleted.')
        db.execute('DELETE FROM jobs WHERE id = ?', (job_id,))


def owned_jobs(actor):
    require_role(actor, 'Employer')
    results = []
    for row in get_db().execute('SELECT id FROM jobs WHERE employer_id = ? ORDER BY id DESC', (actor['id'],)):
        result = _job(row['id'])
        result['applicant_count'] = get_db().execute(
            'SELECT count(*) FROM applications WHERE job_id = ?', (row['id'],)).fetchone()[0]
        results.append(result)
    return results


def recommendations(actor, skills=None):
    require_role(actor, 'Candidate')
    skills = skills_for(actor['id']) if skills is None else normalize_skills(skills)
    applied = {r['job_id'] for r in get_db().execute('SELECT job_id FROM applications WHERE candidate_id = ?', (actor['id'],))}
    results = []
    for row in get_db().execute('SELECT id FROM jobs'):
        result = _job(row['id'])
        result.update(score=score(skills, result['skills']), applied=result['id'] in applied)
        results.append(result)
    return sorted(results, key=lambda j: (-j['score'], j['title'].lower(), j['id']))


def booking_for(application_id):
    row = get_db().execute(
        'SELECT b.id, b.slot_id, s.starts_at, s.ends_at FROM bookings b '
        'JOIN slots s ON s.id = b.slot_id WHERE b.application_id = ?', (application_id,)).fetchone()
    return dict(row) if row else None


def application_record(application_id):
    row = get_db().execute(
        'SELECT a.*, j.employer_id, j.title, c.name AS company_name, u.display_name, u.email '
        'FROM applications a JOIN jobs j ON j.id = a.job_id '
        'JOIN companies c ON c.employer_id = j.employer_id '
        'JOIN users u ON u.id = a.candidate_id WHERE a.id = ?', (application_id,)).fetchone()
    if row is None:
        raise DomainError(404, 'Application not found.')
    result = dict(row)
    result['booking'] = booking_for(application_id)
    return result


def application(actor, application_id):
    require_role(actor, 'Candidate')
    result = application_record(application_id)
    require_owner(actor, result['candidate_id'])
    return result


def applications(actor):
    require_role(actor, 'Candidate')
    return [application(actor, r['id']) for r in get_db().execute(
        'SELECT id FROM applications WHERE candidate_id = ? ORDER BY id DESC', (actor['id'],))]


def apply(actor, job_id):
    require_role(actor, 'Candidate')
    with transaction() as db:
        posting = job(actor, job_id)
        if posting['posting_status'] == 'Closed':
            raise DomainError(409, 'This job is closed to new applications.')
        if db.execute('SELECT 1 FROM applications WHERE candidate_id = ? AND job_id = ?', (actor['id'], job_id)).fetchone():
            raise DomainError(409, 'You have already applied to this job.')
        application_id = db.execute(
            'INSERT INTO applications(candidate_id,job_id,created_at) VALUES (?,?,?)',
            (actor['id'], job_id, int(current_app.config['NOW']().timestamp()))).lastrowid
    return application(actor, application_id)


def applicants(actor, job_id):
    require_role(actor, 'Employer')
    posting = job(actor, job_id)
    results = []
    for row in get_db().execute('SELECT id FROM applications WHERE job_id = ?', (job_id,)):
        result = application_record(row['id'])
        result['skills'] = skills_for(result['candidate_id'])
        result['score'] = score(result['skills'], posting['skills'])
        results.append(result)
    return sorted(results, key=lambda a: (-a['score'], a['display_name'].lower(), a['candidate_id']))


def ranked_applications(actor):
    """Rank only this employer's applications with the same per-job score logic."""
    require_role(actor, 'Employer')
    rows = [applicant for posting in owned_jobs(actor)
            for applicant in applicants(actor, posting['id'])]
    return sorted(rows, key=lambda a: (
        -a['score'], a['display_name'].lower(), a['candidate_id'], a['id']))


def set_status(actor, application_id, status):
    require_role(actor, 'Employer')
    with transaction() as db:
        result = application_record(application_id)
        require_owner(actor, result['employer_id'])
        if status not in STATUSES:
            raise DomainError(400, 'Choose a valid application status.')
        db.execute('UPDATE applications SET status = ? WHERE id = ?', (status, application_id))
    return application_record(application_id)
