"""UTC availability and database-atomic interview booking."""
from datetime import datetime, timezone

from flask import current_app

from .accounts import require_owner, require_role
from .db import get_db, transaction
from .errors import DomainError
from . import jobs


def now_timestamp():
    return current_app.config['NOW']().timestamp()


def parse_time(value):
    try:
        result = datetime.fromisoformat(value)
        if result.tzinfo is None or result.utcoffset() is None or result.microsecond:
            raise ValueError
        # Validate the normalized date before persisting it; an offset can push
        # an otherwise valid local year beyond datetime's UTC rendering range.
        return int(result.astimezone(timezone.utc).timestamp())
    except (TypeError, ValueError, OverflowError) as error:
        raise DomainError(400, 'Use a valid date and time with an explicit timezone and whole seconds.') from error


def format_time(timestamp):
    return datetime.fromtimestamp(timestamp, timezone.utc).strftime('%d %b %Y, %H:%M UTC')


def slot(slot_id):
    row = get_db().execute(
        'SELECT s.*, j.employer_id, j.title, c.name AS company_name, b.application_id FROM slots s '
        'JOIN jobs j ON j.id = s.job_id JOIN companies c ON c.employer_id = j.employer_id '
        'LEFT JOIN bookings b ON b.slot_id = s.id WHERE s.id = ?', (slot_id,)).fetchone()
    if row is None:
        raise DomainError(404, 'Interview slot not found.')
    return dict(row)


def create_slot(actor, job_id, start, end):
    require_role(actor, 'Employer')
    with transaction() as db:
        if job_id is None:
            anchor = db.execute('SELECT id FROM jobs WHERE employer_id = ? ORDER BY id LIMIT 1', (actor['id'],)).fetchone()
            if anchor is None:
                raise DomainError(400, 'Create a job before adding interview times.')
            job_id = anchor['id']
        else:
            jobs.job(actor, job_id)
        start_time, end_time = parse_time(start), parse_time(end)
        if end_time - start_time != 1800:
            raise DomainError(400, 'Interview slots must last exactly 30 minutes.')
        if start_time <= now_timestamp():
            raise DomainError(400, 'Choose a future interview time.')
        if db.execute(
            'SELECT 1 FROM slots s JOIN jobs j ON j.id = s.job_id '
            'WHERE j.employer_id = ? AND s.starts_at < ? AND s.ends_at > ? LIMIT 1',
            (actor['id'], end_time, start_time),
        ).fetchone():
            raise DomainError(409, 'That overlaps another interview time.')
        slot_id = db.execute('INSERT INTO slots(job_id,starts_at,ends_at) VALUES (?,?,?)',
                             (job_id, start_time, end_time)).lastrowid
        return slot(slot_id)


def delete_slot(actor, slot_id):
    require_role(actor, 'Employer')
    with transaction() as db:
        result = slot(slot_id)
        require_owner(actor, result['employer_id'])
        if result['application_id'] is not None:
            raise DomainError(409, 'Booked slots cannot be deleted.')
        db.execute('DELETE FROM slots WHERE id = ?', (slot_id,))


def employer_slots(actor):
    require_role(actor, 'Employer')
    return [slot(r['id']) for r in get_db().execute(
        'SELECT s.id FROM slots s JOIN jobs j ON j.id = s.job_id '
        'WHERE j.employer_id = ? ORDER BY s.starts_at, s.id', (actor['id'],))]


def available_slots(actor, application_id):
    application = jobs.application(actor, application_id)
    if application['status'] != 'Interviewing' or application['booking'] is not None:
        return []
    return [dict(r) for r in get_db().execute(
        'SELECT s.* FROM slots s JOIN jobs j ON j.id = s.job_id '
        'LEFT JOIN bookings b ON b.slot_id = s.id '
        'WHERE j.employer_id = ? AND s.starts_at > ? AND b.id IS NULL ORDER BY s.starts_at, s.id',
        (application['employer_id'], now_timestamp()))]


def book(actor, application_id, slot_id):
    require_role(actor, 'Candidate')
    # BEGIN IMMEDIATE acquires SQLite's write reservation before reading eligibility.
    # The second writer waits, then reads the committed booking and returns 409.
    with transaction() as db:
        application = jobs.application(actor, application_id)
        # Check the application before looking up anyone else's availability.
        if application['booking'] is not None:
            raise DomainError(409, 'This application already has an interview booking.')
        if application['status'] != 'Interviewing':
            raise DomainError(409, 'Only Interviewing applications can book an interview.')
        availability = slot(slot_id)
        if availability['employer_id'] != application['employer_id']:
            raise DomainError(403, 'Choose a slot belonging to this application\'s employer.')
        if availability['starts_at'] <= now_timestamp():
            raise DomainError(409, 'This interview slot is no longer in the future.')
        if availability['application_id'] is not None:
            raise DomainError(409, 'Slot already booked')
        db.execute('INSERT INTO bookings(application_id,slot_id) VALUES (?,?)', (application_id, slot_id))
    return jobs.booking_for(application_id)
