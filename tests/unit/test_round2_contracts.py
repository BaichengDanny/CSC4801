"""Round 2: spec oracles, bounded generators, and rejected-write invariants.

The fixed clock and synthetic people come from conftest.py. Limits (100 skills,
80 chars, text lengths) are existing service choices, not extra course MUSTs.
No generated case talks to a network or to a shared database.
"""
from datetime import datetime, timezone
from fractions import Fraction
import random

import pytest

SEED = 48012026


def snapshot():
    """Compare all application tables, not just the row the request targeted."""
    from recruiting.db import get_db
    db = get_db()
    tables = ('users', 'candidate_profiles', 'candidate_skills', 'companies',
              'jobs', 'job_skills', 'applications', 'slots', 'bookings')
    return {table: sorted(tuple(row) for row in db.execute('SELECT * FROM ' + table))
            for table in tables}


def client_for(app, actor):
    client = app.test_client()
    response = client.post('/api/auth/login', json={
        'email': actor['email'], 'password': 'DemoPass123!', 'role': actor['role']})
    assert response.status_code == 200
    return client


def assert_rejected(client, path, data, status):
    before = snapshot()
    response = client.post(path, json=data)
    assert response.status_code == status, (path, data, response.get_data(as_text=True))
    assert response.is_json and response.json['ok'] is False
    assert snapshot() == before, (path, 'rejected request changed application data')
    return response


@pytest.mark.parametrize(('candidate', 'required', 'expected'), [
    (['Python', 'SQL'], ['Python', 'SQL'], 100),
    (['Python'], ['Python', 'SQL'], 50),
    (['Rust'], ['Python', 'SQL'], 0),
    (['anything'], [], 100),
    ([], ['Python'], 0),
    (['a'], ['a', 'b', 'c'], 33),
    (['a', 'b'], ['a', 'b', 'c'], 66),
    ([' PYTHON ', 'python', '', '  '], ['python', ' SQL ', 'sql'], 50),
])
def test_independent_golden_scores(candidate, required, expected):
    from recruiting.matching import score
    actual = score(candidate, required)
    assert type(actual) is int
    assert actual == expected


def test_documented_skill_limits_and_types():
    from recruiting.matching import normalize_skills
    from recruiting.errors import DomainError
    assert normalize_skills([]) == []
    assert normalize_skills([' ', '\t', '\n']) == []
    assert normalize_skills([' A ', 'a'] * 101) == ['a']
    assert normalize_skills(['x' * 80]) == ['x' * 80]
    assert len(normalize_skills(['s' + str(i) for i in range(100)])) == 100
    for value in (None, 'Python', {}, True, 7, [None], [1], [False], [['a']],
                  ['x' * 81], ['s' + str(i) for i in range(101)]):
        with pytest.raises(DomainError) as caught:
            normalize_skills(value)
        assert caught.value.status == 400, repr(value)


def test_seeded_score_oracle_and_metamorphic_relations():
    from recruiting.matching import score
    rng = random.Random(SEED)
    vocabulary = ['python', 'sql', 'rust', 'go', 'c++', 'c#', '机器学习', 'é']
    for index in range(400):
        candidate = rng.sample(vocabulary, rng.randrange(len(vocabulary) + 1))
        required = rng.sample(vocabulary, rng.randrange(len(vocabulary) + 1))
        # Integer part of an independently calculated rational number.
        expected = 100 if not required else int(Fraction(
            100 * sum(skill in candidate for skill in required), len(required)))
        actual = score(candidate, required)
        witness = (SEED, index, candidate, required)
        assert type(actual) is int and 0 <= actual <= 100, witness
        assert actual == expected, witness
        noisy_candidate = [' \t' + skill.upper() + '\n' for skill in candidate * 2] + ['', ' ']
        noisy_required = [' ' + skill.upper() + ' ' for skill in required * 2] + ['\t']
        rng.shuffle(noisy_candidate)
        rng.shuffle(noisy_required)
        assert score(noisy_candidate, noisy_required) == expected, witness
        missing = [skill for skill in required if skill not in candidate]
        if missing:
            after = score(candidate + [missing[0]], required)
            assert after >= actual, witness
            assert after == int(Fraction(100 * (sum(s in candidate for s in required) + 1),
                                         len(required))), witness


def test_both_views_recompute_oracle_and_stable_ties(people):
    from recruiting import accounts, jobs
    c, c2, e = people['candidate'], people['candidate2'], people['employer']
    accounts.update_profile(c, 'same', ['a', 'b'], 'resume must not affect score')
    accounts.update_profile(c2, 'SAME', ['a', 'b'], 'completely different resume')
    definitions = [('Zulu', ['a', 'b', 'c'], 66), ('alpha', ['a', 'b', 'c'], 66),
                   ('ALPHA', ['a', 'b', 'c'], 66), ('Empty', [], 100),
                   ('Zero', ['rust'], 0), ('third', ['a', 'b', 'c', 'd', 'e', 'f'], 33)]
    records = [jobs.create_job(e, title, 'Description', required)
               for title, required, expected in definitions]
    expected_by_id = {row['id']: definition[2] for row, definition in zip(records, definitions)}
    expected_order = [records[i]['id'] for i in (3, 1, 2, 0, 5, 4)]
    rows = jobs.recommendations(c)
    assert [row['id'] for row in rows] == expected_order
    assert {row['id']: row['score'] for row in rows} == expected_by_id
    for row in records:
        # Apply in reverse identity order to prevent insertion order hiding a bad tie break.
        jobs.apply(c2, row['id'])
        jobs.apply(c, row['id'])
        applicants = jobs.applicants(e, row['id'])
        assert [a['candidate_id'] for a in applicants] == [c['id'], c2['id']]
        assert [a['score'] for a in applicants] == [expected_by_id[row['id']]] * 2
    accounts.update_profile(c, 'same', ['a', 'b', 'c'], 'changed private text')
    assert next(j for j in jobs.recommendations(c) if j['id'] == records[0]['id'])['score'] == 100
    assert jobs.applicants(e, records[0]['id'])[0]['score'] == 100
    jobs.update_job(e, records[0]['id'], 'Zulu', 'Description', ['a', 'z'])
    assert next(j for j in jobs.recommendations(c) if j['id'] == records[0]['id'])['score'] == 50
    assert jobs.applicants(e, records[0]['id'])[0]['score'] == 50


@pytest.mark.parametrize(('raw', 'label'), [
    ('true', 'boolean'), ('1.5', 'fractional'), ('1e400', 'overflow'),
], ids=lambda value: value)
def test_json_resource_id_does_not_coerce_or_crash(app, people, raw, label):
    from recruiting import jobs, scheduling
    j = jobs.create_job(people['employer'], 'Role', 'Description', [])
    a = jobs.apply(people['candidate2'], j['id'])
    jobs.set_status(people['employer'], a['id'], 'Interviewing')
    scheduling.create_slot(people['employer'], j['id'],
                           '2030-01-02T10:00:00Z', '2030-01-02T10:30:00Z')
    apply_client = client_for(app, people['candidate'])
    book_client = client_for(app, people['candidate2'])
    for client, path, key in (
        (apply_client, '/api/candidate/applications', 'jobId'),
        (book_client, '/api/candidate/applications/' + str(a['id']) + '/book', 'slotId'),
    ):
        before = snapshot()
        response = client.post(path, data='{"' + key + '":' + raw + '}',
                               content_type='application/json')
        assert response.status_code == 404, (label, response.get_data(as_text=True))
        assert snapshot() == before


def test_missing_json_ids_and_string_ids_preserve_contract(app, people):
    from recruiting import jobs
    j = jobs.create_job(people['employer'], 'Role', 'Description', [])
    client = client_for(app, people['candidate'])
    for value in (None, [], {}, False, 0, -1, 2**63, '9' * 5000, 'x', '1 OR 1=1'):
        assert_rejected(client, '/api/candidate/applications', {'jobId': value}, 404)
    response = client.post('/api/candidate/applications', json={'jobId': str(j['id'])})
    assert response.status_code == 201 and response.json['application']['jobId'] == str(j['id'])


@pytest.mark.parametrize('target', ['candidate/profile', 'employer/company', 'employer/jobs/1'])
def test_non_object_and_malformed_json_are_rejected(app, people, target):
    from recruiting import jobs
    jobs.create_job(people['employer'], 'Role', 'Description', [])
    actor = people['candidate'] if target.startswith('candidate') else people['employer']
    client = client_for(app, actor)
    for raw in ('null', '{', '', '[]', 'true', '1', '"text"', '{"name":'):
        before = snapshot()
        response = client.post('/api/' + target, data=raw, content_type='application/json')
        assert response.status_code == 400, (target, raw, response.get_data(as_text=True))
        assert snapshot() == before
    # An explicit empty object remains a supported no-op partial update.
    assert client.post('/api/' + target, json={}).status_code == 200


def test_failed_writes_leave_all_related_and_unrelated_rows(app, people):
    from recruiting import accounts, jobs
    e, c = people['employer'], people['candidate']
    j = jobs.create_job(e, 'Original', 'Original body', ['python'])
    jobs.create_job(people['employer2'], 'Unrelated', 'Keep untouched', ['go'])
    candidate, employer = client_for(app, c), client_for(app, e)
    for invalid in ({'name': ''}, {'name': 'x' * 101}, {'skills': 'python'},
                    {'skills': [False]}, {'resume': 'x' * 50001}, {'resume': '\x00'},
                    {'name': 'Changed', 'skills': ['new'], 'location': 'x' * 121}):
        assert_rejected(candidate, '/api/candidate/profile', invalid, 400)
    for invalid in ({'name': ''}, {'about': 'x' * 10001},
                    {'name': 'Changed', 'website': 'x' * 201}):
        assert_rejected(employer, '/api/employer/company', invalid, 400)
    for invalid in ({'title': ''}, {'title': 'x' * 151}, {'skills': ['x' * 81]},
                    {'title': 'Changed', 'body': 'x' * 10001},
                    {'title': 'Changed', 'desc': 'x' * 301},
                    {'title': 'Changed', 'location': 'x' * 121},
                    {'title': 'Changed', 'type': 'invalid'}, {'status': 'invalid'}):
        assert_rejected(employer, '/api/employer/jobs/' + str(j['id']), invalid, 400)
    assert candidate.post('/api/candidate/applications', json={'jobId': j['id']}).status_code == 201
    assert_rejected(candidate, '/api/candidate/applications', {'jobId': j['id']}, 409)
    assert_rejected(employer, '/api/employer/jobs/' + str(j['id']) + '/delete', {}, 409)
    # Maximum documented lengths remain accepted, avoiding validation over-tightening.
    assert candidate.post('/api/candidate/profile', json={
        'name': 'n' * 100, 'resume': 'r' * 50000, 'skills': ['s' * 80]}).status_code == 200
    assert employer.post('/api/employer/jobs/' + str(j['id']), json={
        'title': 't' * 150, 'body': 'b' * 10000, 'desc': 'd' * 300,
        'location': 'l' * 120}).status_code == 200
    assert accounts.skills_for(c['id']) == ['s' * 80]


def test_time_boundaries_offsets_and_failed_state(app, people):
    from recruiting import jobs, scheduling
    j = jobs.create_job(people['employer'], 'Role', 'Description', [])
    client = client_for(app, people['employer'])
    invalid = [
        (None, None), (True, False), (42, 43), ([], {}),
        ('2030-01-02', '2030-01-02'), ('bad', 'worse'),
        ('2030-01-02T10:00:00', '2030-01-02T10:30:00'),
        ('2030-01-02T10:00:00Z', '2030-01-02T10:29:59Z'),
        ('2030-01-02T10:00:00Z', '2030-01-02T10:30:01Z'),
        ('2030-01-02T10:00:00Z', '2030-01-02T09:30:00Z'),
        ('2030-01-02T10:00:00.001Z', '2030-01-02T10:30:00.001Z'),
        ('2030-01-01T09:00:00Z', '2030-01-01T09:30:00Z'),
        ('2030-01-01T08:59:59Z', '2030-01-01T09:29:59Z'),
        ('2030-02-29T10:00:00Z', '2030-02-29T10:30:00Z'),
        ('9999-12-31T23:00:00-23:59', '9999-12-31T23:30:00-23:59'),
    ]
    for start, end in invalid:
        assert_rejected(client, '/api/employer/slots', {'start': start, 'end': end}, 400)
    assert client.post('/api/employer/slots', json={
        'start': '2030-01-01T09:00:01Z', 'end': '2030-01-01T09:30:01Z'}).status_code == 201
    for value in ('2030-01-02T10:00:00Z', '2030-01-02T18:00:00+08:00',
                  '2030-01-02T02:00:00-08:00', '2030-01-02T10:00:00.000+00:00'):
        assert scheduling.parse_time(value) == 1893578400
    assert scheduling.parse_time('2032-02-29T10:00:00Z') == int(
        datetime(2032, 2, 29, 10, tzinfo=timezone.utc).timestamp())


def test_seeded_structured_invalid_json_and_time_inputs(app, people):
    from recruiting import jobs
    from recruiting.db import get_db
    jobs.create_job(people['employer'], 'Role', 'Description', [])
    employer = client_for(app, people['employer'])
    candidate = client_for(app, people['candidate'])
    rng = random.Random(SEED)
    # Generate only partitions with a spec- or documented-validation-based oracle.
    for index in range(80):
        value = rng.choice([None, True, rng.randrange(-20, 20), {}, [['nested']]])
        assert_rejected(candidate, '/api/candidate/profile', {'skills': value}, 400)
        month = rng.choice([0, 13, 99])
        start = '2030-' + str(month).zfill(2) + '-02T10:00:00Z'
        assert_rejected(employer, '/api/employer/slots',
                        {'start': start, 'end': '2030-01-02T10:30:00Z'}, 400)
    assert get_db().execute('PRAGMA foreign_key_check').fetchall() == []


def test_booking_state_machine_and_exact_future_boundary(app, people):
    from recruiting import jobs, scheduling
    e, c = people['employer'], people['candidate']
    anchor = jobs.create_job(e, 'Anchor role', 'Description', [])
    other_job = jobs.create_job(e, 'Application role', 'Description', [])
    foreign_job = jobs.create_job(people['employer2'], 'Foreign', 'Description', [])
    a = jobs.apply(c, other_job['id'])
    good = scheduling.create_slot(e, anchor['id'], '2030-01-02T10:00:00Z', '2030-01-02T10:30:00Z')
    foreign = scheduling.create_slot(people['employer2'], foreign_job['id'],
                                    '2030-01-02T10:00:00Z', '2030-01-02T10:30:00Z')
    candidate, employer = client_for(app, c), client_for(app, e)
    path = '/api/candidate/applications/' + str(a['id']) + '/book'
    assert a['status'] == 'Pending'
    for status in ('Pending', 'Rejected', 'Accepted'):
        jobs.set_status(e, a['id'], status)
        assert scheduling.available_slots(c, a['id']) == []
        assert_rejected(candidate, path, {'slotId': good['id']}, 409)
    jobs.set_status(e, a['id'], 'Interviewing')
    assert_rejected(candidate, path, {'slotId': foreign['id']}, 403)
    assert_rejected(candidate, path, {'slotId': 999}, 404)
    # Equality with NOW is past; one second before start is still eligible.
    app.config['NOW'] = lambda: datetime(2030, 1, 2, 10, tzinfo=timezone.utc)
    candidate, employer = client_for(app, c), client_for(app, e)
    assert scheduling.available_slots(c, a['id']) == []
    assert_rejected(candidate, path, {'slotId': good['id']}, 409)
    app.config['NOW'] = lambda: datetime(2030, 1, 2, 9, 59, 59, tzinfo=timezone.utc)
    assert [s['id'] for s in scheduling.available_slots(c, a['id'])] == [good['id']]
    assert candidate.post(path, json={'slotId': good['id']}).status_code == 200
    assert_rejected(candidate, path, {'slotId': good['id']}, 409)
    extra = scheduling.create_slot(e, anchor['id'], '2030-01-02T11:00:00Z', '2030-01-02T11:30:00Z')
    assert_rejected(candidate, path, {'slotId': extra['id']}, 409)
    for status in ('Accepted', 'Rejected', 'Pending', 'Interviewing'):
        assert employer.post('/api/employer/applications/' + str(a['id']) + '/status',
                             json={'status': status}).status_code == 200
        assert jobs.application(c, a['id'])['booking']['slot_id'] == good['id']
        assert jobs.applicants(e, other_job['id'])[0]['booking']['slot_id'] == good['id']
        assert scheduling.available_slots(c, a['id']) == []
    assert_rejected(employer, '/api/employer/slots/' + str(good['id']) + '/delete', {}, 409)
    assert_rejected(employer, '/api/employer/jobs/' + str(anchor['id']) + '/delete', {}, 409)


def test_role_owner_matrix_with_direct_requests(app, people):
    from recruiting import jobs, scheduling, accounts
    c, e = people['candidate'], people['employer']
    accounts.update_profile(c, 'Alex', ['python'], 'ROUND2_PRIVATE_RESUME_SENTINEL')
    j = jobs.create_job(e, 'Owned role', 'Description', [])
    a = jobs.apply(c, j['id'])
    s = scheduling.create_slot(e, j['id'], '2030-01-02T10:00:00Z', '2030-01-02T10:30:00Z')
    sessions = {name: client_for(app, person) for name, person in people.items()}
    sessions['anonymous'] = app.test_client()
    operations = [
        ('/api/employer/jobs/' + str(j['id']), {'title': 'Taken'}),
        ('/api/employer/jobs/' + str(j['id']) + '/delete', {}),
        ('/api/employer/applications/' + str(a['id']) + '/status', {'status': 'Accepted'}),
        ('/api/employer/slots/' + str(s['id']) + '/delete', {}),
    ]
    for name in ('anonymous', 'candidate', 'candidate2', 'employer2'):
        for path, data in operations:
            assert_rejected(sessions[name], path, data, 401 if name == 'anonymous' else 403)
    book = '/api/candidate/applications/' + str(a['id']) + '/book'
    for name in ('anonymous', 'candidate2', 'employer', 'employer2'):
        assert_rejected(sessions[name], book, {'slotId': s['id']}, 401 if name == 'anonymous' else 403)
    # Privacy endpoints are deliberately owner-only service methods; no public
    # arbitrary-ID profile API exists. Exercise the representative direct boundary.
    from recruiting.errors import DomainError
    for actor in (people['candidate2'], e, people['employer2']):
        before = snapshot()
        with pytest.raises(DomainError) as caught:
            accounts.profile(actor, c['id'])
        assert caught.value.status == 403 and snapshot() == before
    for name in ('candidate2', 'employer', 'employer2'):
        prefix = 'candidate' if name == 'candidate2' else 'employer'
        response = sessions[name].get('/api/' + prefix + '/bootstrap')
        assert response.status_code == 200
        text = response.get_data(as_text=True)
        assert 'ROUND2_PRIVATE_RESUME_SENTINEL' not in text and 'password_hash' not in text
    assert_rejected(sessions['employer'], '/api/employer/jobs/999', {'title': 'Missing'}, 404)
    assert_rejected(sessions['candidate'], '/api/candidate/applications/999/book', {'slotId': s['id']}, 404)


def test_nested_request_transactions_roll_back_and_remain_usable(app, people):
    from recruiting.db import get_db, transaction
    from recruiting import jobs
    from recruiting.errors import DomainError
    db = get_db()
    before = snapshot()
    with pytest.raises(DomainError):
        with transaction():
            jobs.create_job(people['employer'], 'Rollback', 'Description', [])
            raise DomainError(400, 'synthetic late failure')
    assert snapshot() == before and not db.in_transaction
    with transaction():
        jobs.create_job(people['employer'], 'Keep', 'Description', [])
        with pytest.raises(DomainError):
            with transaction():
                jobs.create_job(people['employer'], 'Discard', 'Description', [])
                raise DomainError(400, 'synthetic inner failure')
    assert [r['title'] for r in jobs.owned_jobs(people['employer'])] == ['Keep']
    assert not db.in_transaction


def test_storage_contention_is_distinct_and_transaction_recovers(app, people):
    import sqlite3
    from recruiting import jobs
    from recruiting.db import get_db, transaction
    from recruiting.errors import DomainError
    db = get_db()
    db.execute('PRAGMA busy_timeout = 0')
    blocker = sqlite3.connect(app.config['DATABASE'], isolation_level=None)
    before = snapshot()
    try:
        blocker.execute('BEGIN IMMEDIATE')
        with pytest.raises(DomainError) as caught:
            with transaction():
                raise AssertionError('must not enter a transaction without its write reservation')
        assert caught.value.status == 503
        assert caught.value.message != 'Slot already booked'
    finally:
        blocker.rollback()
        blocker.close()
    assert snapshot() == before and not db.in_transaction
    with pytest.raises(sqlite3.OperationalError):
        with transaction():
            db.execute('SELECT * FROM deliberately_missing_table')
    assert snapshot() == before and not db.in_transaction
    assert jobs.create_job(people['employer'], 'Recovered', 'Description', [])['title'] == 'Recovered'


def test_same_name_companies_remain_distinct_in_candidate_api(app, people):
    from recruiting import accounts, jobs
    e1, e2 = people['employer'], people['employer2']
    accounts.update_company(e1, 'Same company', 'First employer description')
    accounts.update_company(e2, 'Same company', 'Second employer description')
    j1 = jobs.create_job(e1, 'First', 'Role one', [])
    j2 = jobs.create_job(e2, 'Second', 'Role two', [])
    result = client_for(app, people['candidate']).get('/api/candidate/bootstrap').json
    cards = {job['id']: job for job in result['jobs']}
    for job, owner, description in ((j1, e1, 'First employer description'),
                                     (j2, e2, 'Second employer description')):
        card = cards[str(job['id'])]
        assert card['employerId'] == str(owner['id'])
        assert result['companies'][card['employerId']]['about'] == description


def test_new_employer_cannot_offer_slots_without_a_job(app, people):
    client = client_for(app, people['employer'])
    assert_rejected(client, '/api/employer/slots', {
        'start': '2030-01-02T10:00:00Z', 'end': '2030-01-02T10:30:00Z'}, 400)


def test_booked_slot_is_redacted_and_unavailable_to_other_candidate(app, people):
    from recruiting import jobs, scheduling
    e, c, other = people['employer'], people['candidate'], people['candidate2']
    j = jobs.create_job(e, 'Role', 'Description', [])
    own_app, other_app = jobs.apply(c, j['id']), jobs.apply(other, j['id'])
    for application in (own_app, other_app):
        jobs.set_status(e, application['id'], 'Interviewing')
    slot = scheduling.create_slot(e, j['id'], '2030-01-02T10:00:00Z', '2030-01-02T10:30:00Z')
    scheduling.book(c, own_app['id'], slot['id'])
    own = client_for(app, c).get('/api/candidate/bootstrap').json
    theirs = client_for(app, other).get('/api/candidate/bootstrap').json
    employer = client_for(app, e).get('/api/employer/bootstrap').json
    assert own['state']['slots'][0]['bookedBy'] == str(own_app['id'])
    # The team branch strengthens redaction to complete omission; keep
    # asserting the privacy boundary plus the owner's/employer's booking.
    assert theirs['state']['slots'] == []
    assert str(own_app['id']) not in {s['bookedBy'] for s in theirs['state']['slots']}
    assert employer['state']['slots'][0]['bookedBy'] == str(own_app['id'])
    assert scheduling.available_slots(other, other_app['id']) == []
    assert scheduling.employer_slots(e)[0]['application_id'] == own_app['id']


def test_request_size_limit_rejects_without_writes(app, people):
    client = client_for(app, people['candidate'])
    before = snapshot()
    response = client.post('/api/candidate/profile',
                           data='{"resume":"' + ('x' * 1024 * 1024) + '"}',
                           content_type='application/json')
    assert response.status_code == 413 and response.is_json
    assert snapshot() == before
