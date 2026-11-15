import pytest

from tests.unit.test_web import login, token


@pytest.mark.parametrize('resource', ['jobs', 'applications'])
@pytest.mark.parametrize('identifier', ['9223372036854775808', '9' * 5000], ids=['sqlite-overflow', 'conversion-limit'])
def test_oversized_path_id_is_not_found(app, people, resource, identifier):
    client = app.test_client()
    login(client)
    assert client.get(f'/{resource}/{identifier}').status_code == 404


def test_non_ascii_csrf_is_rejected_without_crashing(app, people):
    client = app.test_client()
    token(client)
    response = client.post('/login', data={'email': 'alex@example.test', 'password': 'DemoPass123!', 'csrf_token': '你好'})
    assert response.status_code == 400
    login(client)
    assert client.post('/logout', data={'csrf_token': '你好'}).status_code == 400
    assert client.get('/dashboard').status_code == 200


def test_nul_text_is_rejected_without_partial_changes(app, people):
    from recruiting import accounts, jobs
    from recruiting.errors import DomainError
    from recruiting.db import get_db
    c, e = people['candidate'], people['employer']
    client = app.test_client()
    login(client)
    response = client.post('/profile', data={
        'display_name': '\x00Alex', 'skills': 'Rust', 'resume': 'Changed', 'csrf_token': token(client, '/profile'),
    })
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


def test_forbidden_scheduling_requests_are_403_even_with_malformed_forms(app, people):
    from recruiting import jobs
    from recruiting.db import get_db
    j = jobs.create_job(people['employer'], 'Engineer', 'Description', [])
    a = jobs.apply(people['candidate'], j['id'])
    attempts = [
        ('alex@example.test', f'/jobs/{j["id"]}/slots', {'start': 'bad'}),
        ('field@example.test', f'/jobs/{j["id"]}/slots', {'start': 'bad'}),
        ('field@example.test', f'/applications/{a["id"]}/book', {}),
        ('blair@example.test', f'/applications/{a["id"]}/book', {}),
    ]
    for email, path, form in attempts:
        client = app.test_client()
        login(client, email)
        response = client.post(path, data={**form, 'csrf_token': token(client, '/dashboard')})
        assert response.status_code == 403, (email, path)
    owner = app.test_client()
    login(owner, 'north@example.test')
    response = owner.post(f'/jobs/{j["id"]}/slots', data={'start': 'bad', 'csrf_token': token(owner, '/dashboard')})
    assert response.status_code == 400
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
