"""Regression tests for Matchwork workflow and display fixes."""
import json
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from tests.unit.test_api import login


def as_candidate(app, email='alex@example.test'):
    client = app.test_client()
    assert login(client, email, 'Candidate').status_code == 200
    return client


def as_employer(app, email='north@example.test'):
    client = app.test_client()
    assert login(client, email, 'Employer').status_code == 200
    return client


def test_api_sends_the_server_match_score_to_both_portals(app, people):
    """Audit defect 1: both pages display recruiting.matching.score, not a second copy."""
    from recruiting import jobs, matching
    from recruiting.accounts import update_profile
    from recruiting.db import get_db

    backend = jobs.create_job(people['employer'], 'Backend', 'APIs', ['Python', 'SQL'])
    jobs.create_job(people['employer'], 'Open', 'Anyone', [])
    application = jobs.apply(people['candidate2'], backend['id'])
    # The server normalizes a leading byte-order mark the same way in both portals.
    update_profile(people['candidate2'], 'Blair Chen', ['\ufeffpython', 'sql'], '')
    stored = {row[0] for row in get_db().execute('SELECT skill FROM candidate_skills WHERE candidate_id = ?',
                                                 (people['candidate2']['id'],))}
    assert stored == {'python', 'sql'}
    expected = matching.score(['\ufeffpython', 'sql'], ['python', 'sql'])
    assert expected == 100

    blair = as_candidate(app, 'blair@example.test')
    cards = {card['title']: card for card in blair.get('/api/candidate/bootstrap').get_json()['jobs']}
    assert cards['Backend']['score'] == expected
    assert cards['Open']['score'] == 100

    north = as_employer(app)
    rows = north.get('/api/employer/bootstrap').get_json()['state']['applications']
    assert [row['score'] for row in rows if row['id'] == str(application['id'])] == [expected]
    changed = north.post(f'/api/employer/applications/{application["id"]}/status', json={'status': 'Interviewing'})
    assert changed.status_code == 200 and changed.get_json()['application']['score'] == expected


def test_match_js_normalizes_exactly_like_python():
    """Audit defect 1: the offline calculator in match.js must agree on these cases."""
    from recruiting import matching

    node = shutil.which('node')
    assert node, 'Install Node.js to run the Matchwork JavaScript tests (see INSTALL.md).'
    odd = ['\ufeffpython', '\x1cpython\x1f', '\x85sql', '\u00a0Go\u3000', ' RUST ', 'ǅx', 'ΣΑΣ', '']
    cases = [
        [['Python', 'SQL'], ['Python', 'SQL']], [['Python'], ['Python', 'SQL']], [['Rust'], ['Python', 'SQL']],
        [['Go'], []], [odd, ['python', 'sql', 'go', 'rust', 'ǆx', 'σας']], [['a', 'b'], ['a', 'b', 'c']],
    ]
    expected = [{'normalized': sorted(matching.normalize_skills(c)), 'score': matching.score(c, r)} for c, r in cases]
    script = Path(__file__).with_name('match_parity.cjs')
    result = subprocess.run([node, script], input=json.dumps({'cases': cases, 'expected': expected}),
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr


def test_work_preferences_are_saved_and_validated(app, people):
    """Audit defect 3: the profile form's job-type and remote choices persist."""
    alex = as_candidate(app)
    assert alex.get('/api/candidate/bootstrap').get_json()['state']['profile']['prefs'] is None
    saved = alex.post('/api/candidate/profile', json={'prefs': {'type': 'Contract', 'remote': True}})
    assert saved.status_code == 200
    assert saved.get_json()['profile']['prefs'] == {'type': 'Contract', 'remote': True}
    assert alex.post('/api/candidate/profile', json={'name': 'Alex M'}).status_code == 200
    profile = alex.get('/api/candidate/bootstrap').get_json()['state']['profile']
    assert profile['prefs'] == {'type': 'Contract', 'remote': True} and profile['extras'] is True
    for bad in ({'type': 'Weekends', 'remote': False}, {'type': 'Any', 'remote': 'yes'}, ['Any'], 'Any'):
        response = alex.post('/api/candidate/profile', json={'name': 'Changed', 'prefs': bad})
        assert response.status_code == 400
    profile = alex.get('/api/candidate/bootstrap').get_json()['state']['profile']
    assert profile['name'] == 'Alex M' and profile['prefs'] == {'type': 'Contract', 'remote': True}


def test_application_history_and_resume_dates_are_real(app, people):
    """Audit defect 10: history shows when each change happened, and the resume date is stored."""
    from recruiting import jobs, scheduling

    clock = {'now': datetime(2030, 1, 1, 9, tzinfo=timezone.utc)}
    app.config['NOW'] = lambda: clock['now']
    job = jobs.create_job(people['employer'], 'Backend', 'APIs', ['python'])
    application = jobs.apply(people['candidate'], job['id'])
    clock['now'] += timedelta(days=2)
    jobs.set_status(people['employer'], application['id'], 'Interviewing')
    slot = scheduling.create_slot(people['employer'], job['id'], '2030-01-20T18:00:00Z', '2030-01-20T18:30:00Z')
    clock['now'] += timedelta(days=1)
    scheduling.book(people['candidate'], application['id'], slot['id'])
    clock['now'] += timedelta(days=4)
    jobs.set_status(people['employer'], application['id'], 'Accepted')

    alex = as_candidate(app)
    state = alex.get('/api/candidate/bootstrap').get_json()['state']
    record = next(a for a in state['applications'] if a['id'] == str(application['id']))
    assert record['events'] == [
        ['Applied', '2030-01-01T09:00:00+00:00'],
        ['Moved to Interviewing', '2030-01-03T09:00:00+00:00'],
        ['Interview booked', '2030-01-04T09:00:00+00:00'],
        ['Accepted', '2030-01-08T09:00:00+00:00'],
    ]
    north = as_employer(app)
    employer_view = next(a for a in north.get('/api/employer/bootstrap').get_json()['state']['applications']
                         if a['id'] == str(application['id']))
    assert employer_view['events'] == record['events']
    # The people fixture saved Alex's resume at the fixed test clock.
    assert state['profile']['resumeUpdated'] == '2030-01-01T09:00:00+00:00'
    saved = alex.post(f'/api/candidate/{people["candidate"]["id"]}/resume', json={'resume': 'New text'})
    assert saved.status_code == 200
    profile = alex.get('/api/candidate/bootstrap').get_json()['state']['profile']
    assert profile['resumeUpdated'] == '2030-01-08T09:00:00+00:00'


def test_legacy_application_history_does_not_invent_dates(app, people):
    from recruiting import jobs, scheduling
    from recruiting.db import get_db

    employer = people['employer']
    job = jobs.create_job(employer, 'Backend', 'APIs', ['python'])
    application = jobs.apply(people['candidate'], job['id'])
    slot = scheduling.create_slot(employer, job['id'], '2030-01-20T18:00:00Z', '2030-01-20T18:30:00Z')

    # Model the stored state of a booking and status update made before migration 005.
    db = get_db()
    db.execute('UPDATE applications SET status = ? WHERE id = ?', ('Interviewing', application['id']))
    db.execute('INSERT INTO bookings(application_id, slot_id) VALUES (?, ?)', (application['id'], slot['id']))
    alex = as_candidate(app)
    north = as_employer(app)

    applied = ['Applied', '2030-01-01T09:00:00+00:00']
    booking = ['Interview booked', None]
    for client, role in ((alex, 'candidate'), (north, 'employer')):
        state = client.get(f'/api/{role}/bootstrap').get_json()['state']
        record, = state['applications']
        assert record['events'] == [applied, ['Moved to Interviewing', None], booking]
        assert record['slotId'] == str(slot['id'])

    app.config['NOW'] = lambda: datetime(2030, 1, 8, 9, tzinfo=timezone.utc)
    jobs.set_status(employer, application['id'], 'Accepted')
    state = as_candidate(app).get('/api/candidate/bootstrap').get_json()['state']
    record, = state['applications']
    assert record['events'] == [applied, booking, ['Accepted', '2030-01-08T09:00:00+00:00']]


def test_deeply_nested_json_is_a_client_error(app, people):
    """Audit defect 8: a nesting bomb returns 400 instead of crashing the request."""
    alex = as_candidate(app)
    body = '[' * 50_000 + ']' * 50_000
    response = alex.post('/api/candidate/profile', data=body, content_type='application/json')
    assert response.status_code == 400 and response.get_json()['ok'] is False


@pytest.mark.parametrize('value', [True, 1.5, 1.0, '1.0', ' 1', '١', None, [1]])
def test_body_record_ids_must_be_whole_numbers(app, people, value):
    """Audit defect 9: booleans, floats, and padded strings are not record IDs."""
    from recruiting import jobs, scheduling

    job = jobs.create_job(people['employer'], 'Backend', 'APIs', ['python'])
    application = jobs.apply(people['candidate'], job['id'])
    jobs.set_status(people['employer'], application['id'], 'Interviewing')
    slot = scheduling.create_slot(people['employer'], job['id'], '2030-01-02T18:00:00Z', '2030-01-02T18:30:00Z')
    assert slot['id'] == 1
    alex = as_candidate(app)
    response = alex.post(f'/api/candidate/applications/{application["id"]}/book', json={'slotId': value})
    assert response.status_code == 404
    assert jobs.application(people['candidate'], application['id'])['booking'] is None
    assert alex.post('/api/candidate/applications', json={'jobId': value}).status_code == 404
    ok = alex.post(f'/api/candidate/applications/{application["id"]}/book', json={'slotId': '1'})
    assert ok.status_code == 200


def test_job_cards_say_whether_a_location_was_entered(app, people):
    """Audit defect 10: an empty location stays empty instead of becoming 'Remote' or 'Not listed'."""
    north = as_employer(app)
    created = north.post('/api/employer/jobs', json={'title': 'No place', 'desc': 'Summary', 'location': ''})
    assert created.status_code == 201
    card = created.get_json()['job']
    assert card['location'] == 'Not listed' and card['locationSet'] is False
    placed = north.post(f'/api/employer/jobs/{card["id"]}', json={'location': 'Austin, TX'}).get_json()['job']
    assert placed['location'] == 'Austin, TX' and placed['locationSet'] is True


def test_seeded_interviews_are_in_pacific_business_hours(app):
    """Audit defect 10: demo slots start at 18:00 UTC, which is 10:00 or 11:00 Pacific."""
    from recruiting.db import get_db
    from recruiting.seed import seed_demo

    seed_demo(datetime(2030, 1, 1, tzinfo=timezone.utc))
    starts = [row[0] for row in get_db().execute('SELECT starts_at FROM slots ORDER BY starts_at')]
    hours = sorted({datetime.fromtimestamp(s, timezone.utc).hour for s in starts})
    assert hours == [18, 19, 20]
    assert min(starts) == int(datetime(2030, 1, 2, 18, tzinfo=timezone.utc).timestamp())


def test_page_scripts_show_server_scores_real_days_and_real_blockers():
    """Audit defects 1, 6, and 10 in the shipped page scripts (see portal_logic.cjs)."""
    node = shutil.which('node')
    assert node, 'Install Node.js to run the Matchwork JavaScript tests (see INSTALL.md).'
    script = Path(__file__).with_name('portal_logic.cjs')
    result = subprocess.run([node, script], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr
