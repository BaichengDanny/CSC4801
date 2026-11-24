import pytest


def login(client, email, role):
    return client.post('/api/auth/login', json={'email': email, 'password': 'DemoPass123!', 'role': role})


@pytest.mark.parametrize('path', [
    '/api/employer/jobs/{identifier}',
    '/api/candidate/applications/{identifier}/book',
])
@pytest.mark.parametrize('identifier', ['9223372036854775808', '9' * 5000], ids=['sqlite-overflow', 'conversion-limit'])
def test_oversized_path_id_is_not_found(app, people, path, identifier):
    client = app.test_client()
    login(client, 'alex@example.test', 'Candidate')
    assert client.post(path.format(identifier=identifier), json={}).status_code == 404


def test_non_ascii_login_is_rejected_without_crashing(app, people):
    client = app.test_client()
    response = client.post('/api/auth/login', json={
        'email': 'alex@example.test', 'password': '你好', 'role': 'Candidate',
    })
    assert response.status_code == 401
    assert response.mimetype == 'application/json'
    assert login(client, 'alex@example.test', 'Candidate').status_code == 200


def test_nul_text_is_rejected_without_partial_changes(app, people):
    from recruiting import accounts, jobs
    from recruiting.errors import DomainError
    from recruiting.db import get_db
    c, e = people['candidate'], people['employer']
    client = app.test_client()
    login(client, 'alex@example.test', 'Candidate')
    response = client.post('/api/candidate/profile', json={'name': '\x00Alex', 'skills': ['Rust'], 'resume': 'Changed'})
    assert response.status_code == 400
    original = accounts.profile(c, c['id'])
    assert original['display_name'] == 'Alex Morgan'
    assert original['skills'] == ['python', 'sql'] and original['resume'] == 'Private resume'
    with pytest.raises(DomainError) as error:
        accounts.register('new@example.test', 'DemoPass123!', 'Candidate', '\x00New')
    assert error.value.status == 400
    for title, description in [('\x00Title', 'Description'), ('Title', '\x00Description')]:
        with pytest.raises(DomainError) as error:
            jobs.create_job(e, title, description, [])
        assert error.value.status == 400
    assert get_db().execute('SELECT count(*) FROM jobs').fetchone()[0] == 0
    assert get_db().execute('SELECT count(*) FROM users').fetchone()[0] == 4


def test_forbidden_scheduling_requests_are_403_before_bad_input(app, people):
    from recruiting import jobs
    from recruiting.db import get_db
    j = jobs.create_job(people['employer'], 'Engineer', 'Description', [])
    a = jobs.apply(people['candidate'], j['id'])
    candidate = app.test_client()
    login(candidate, 'alex@example.test', 'Candidate')
    assert candidate.post('/api/employer/slots', json={'start': 'bad'}).status_code == 403
    other = app.test_client()
    login(other, 'field@example.test', 'Employer')
    assert other.post(f'/api/candidate/applications/{a["id"]}/book', json={}).status_code == 403
    blair = app.test_client()
    login(blair, 'blair@example.test', 'Candidate')
    assert blair.post(f'/api/candidate/applications/{a["id"]}/book', json={'slotId': 'bad'}).status_code == 403
    owner = app.test_client()
    login(owner, 'north@example.test', 'Employer')
    assert owner.post('/api/employer/slots', json={'start': 'bad'}).status_code == 400
    assert get_db().execute('SELECT count(*) FROM slots').fetchone()[0] == 0
    assert get_db().execute('SELECT count(*) FROM bookings').fetchone()[0] == 0


def test_slot_requires_a_renderable_utc_time(people):
    from recruiting import jobs, scheduling
    from recruiting.db import get_db
    from recruiting.errors import DomainError
    e = people['employer']
    j = jobs.create_job(e, 'Engineer', 'Description', [])
    with pytest.raises(DomainError) as error:
        scheduling.create_slot(e, j['id'], '9999-12-31T23:00:00-01:00', '9999-12-31T23:30:00-01:00')
    assert error.value.status == 400
    assert get_db().execute('SELECT count(*) FROM slots').fetchone()[0] == 0
