"""Map stored records onto the Matchwork page data shape."""
import json
from datetime import datetime, timezone

from flask import current_app

from .matching import normalize_skills

TINTS = (
    ('#1F5FA8', '#EAF1FA'),
    ('#5B3FC4', '#F4F1FD'),
    ('#0F6E7A', '#E9F5F6'),
    ('#B2410F', '#FDF2EA'),
    ('#1F4D34', '#E8F0EA'),
    ('#9A5B00', '#FBF3E4'),
)


def iso(timestamp):
    if not timestamp:
        timestamp = current_app.config['NOW']().timestamp()
    return datetime.fromtimestamp(int(timestamp), timezone.utc).replace(microsecond=0).isoformat()


def paint(name):
    tint, tile = TINTS[sum(ord(char) for char in name or '') % len(TINTS)]
    letter = next((char.upper() for char in name or '' if char.isalnum()), '?')
    return {'mono': letter, 'tint': tint, 'tileBg': tile}


def _logo(row):
    if not row['logo']:
        return {}
    return {'logo': row['logo'], 'w': row['logo_w'] or 32, 'h': row['logo_h'] or 32}


def _categories(row):
    try:
        values = json.loads(row['categories'] or '[]')
    except json.JSONDecodeError:
        return []
    return [str(item) for item in values if str(item).strip()]


def company_card(row):
    name = row['name']
    return {
        'id': str(row['employer_id']),
        'name': name,
        'about': row['description'],
        'industry': row['industry'],
        'size': row['size'],
        'location': row['location'],
        'website': row['website'],
        **paint(name),
        **_logo(row),
    }


def job_card(row):
    summary = row['summary'] or row['description'].split('\n', 1)[0]
    card = {
        'id': str(row['id']),
        'seq': row['id'],
        'title': row['title'],
        'company': row['company_name'],
        'employerId': str(row['employer_id']),
        'owner': str(row['employer_id']),
        'location': row['location'] or 'Not listed',
        'type': row['job_type'] or 'Full-time',
        'status': row['posting_status'] or 'Active',
        'posted': iso(row['created_at']),
        'cats': _categories(row),
        'desc': summary,
        'body': row['description'],
        'skills': normalize_skills(row['skills']),
        **paint(row['company_name']),
        **_logo(row),
    }
    if 'score' in row:
        card.update(score=row['score'], rank=row['rank'])
    return card


def application_events(record):
    applied = iso(record.get('created_at'))
    events = [['Applied', applied]]
    labels = {'Interviewing': 'Moved to Interviewing', 'Rejected': 'Rejected', 'Accepted': 'Accepted', 'Pending': 'Moved back to Pending'}
    if record['status'] != 'Pending':
        events.append([labels[record['status']], applied])
    booking = record.get('booking')
    if booking:
        events.append(['Interview booked', iso(booking['starts_at'])])
    return events


def candidate_application(record):
    booking = record.get('booking')
    return {
        'id': str(record['id']),
        'jobId': str(record['job_id']),
        'status': record['status'],
        'appliedAt': iso(record.get('created_at')),
        'slotId': str(booking['slot_id']) if booking else None,
        'events': application_events(record),
    }


def employer_application(record):
    card = {**candidate_application(record), 'candidateId': str(record['candidate_id'])}
    if 'score' in record:
        card.update(score=record['score'], rank=record['rank'])
    return card


def candidate_profile(actor, details):
    return {
        'name': details['display_name'],
        'headline': details['headline'],
        'location': details['location'],
        'email': actor['email'],
        'skills': normalize_skills(details['skills']),
        'resume': details['resume'],
        'resumeUpdated': iso(None),
        'extras': bool(details['headline'] or details['location']),
    }


def person(row, skills):
    return {
        'id': str(row['candidate_id']),
        'name': row['display_name'],
        'headline': row['headline'],
        'location': row['location'],
        'email': row['email'],
        'skills': normalize_skills(skills),
        'tint': paint(row['display_name'])['tileBg'],
    }


def slot_card(row, company_name, booked_by):
    return {
        'id': str(row['id']),
        'company': company_name,
        'jobId': str(row['job_id']),
        'owner': str(row['employer_id']),
        'start': iso(row['starts_at']),
        'end': iso(row['ends_at']),
        'bookedBy': booked_by,
    }
