from pathlib import Path
import shutil
import subprocess


def test_csrf_token_rotates_after_login(app, people):
    client = app.test_client()
    response = client.get('/api/auth/csrf')
    assert response.status_code == 200
    assert 'no-store' in response.cache_control
    anonymous = response.json['csrfToken']
    assert anonymous and client.get('/api/auth/csrf').json['csrfToken'] == anonymous

    login = client.post('/api/auth/login', csrf=False, headers={'X-CSRF-Token': anonymous}, json={
        'email': 'alex@example.test', 'password': 'DemoPass123!', 'role': 'Candidate',
    })
    assert login.status_code == 200
    signed_in = client.get('/api/auth/me')
    assert signed_in.json['csrfToken'] != anonymous
    assert signed_in.json['csrfToken'] == client.get('/api/auth/csrf').json['csrfToken']
    assert client.post('/api/auth/logout', csrf=False, headers={'X-CSRF-Token': anonymous}).status_code == 403
    assert client.get('/api/auth/me').status_code == 200


def test_account_creation_and_login_require_csrf(app, people):
    client = app.test_client()
    details = {'email': 'alex@example.test', 'password': 'DemoPass123!', 'role': 'Candidate'}
    signup = {**details, 'email': 'new@example.test', 'name': 'New Candidate'}
    assert client.post('/api/auth/login', csrf=False, json=details).status_code == 403
    assert client.get('/api/auth/me').status_code == 401
    assert client.post('/api/auth/register', csrf=False, json=signup).status_code == 403
    assert client.post('/api/auth/register', json=signup).status_code == 201


def test_bodyless_writes_require_this_sessions_csrf_token(app, people):
    from recruiting import jobs, scheduling

    employer = people['employer']
    job = jobs.create_job(employer, 'Engineer', 'Build services', [])
    slot = scheduling.create_slot(employer, job['id'], '2030-01-02T10:00:00Z', '2030-01-02T10:30:00Z')
    client = app.test_client()
    assert client.post('/api/auth/login', json={
        'email': employer['email'], 'password': 'DemoPass123!', 'role': 'Employer',
    }).status_code == 200
    own_token = client.get('/api/auth/me').json['csrfToken']
    other_token = app.test_client().get('/api/auth/csrf').json['csrfToken']

    delete_slot = f'/api/employer/slots/{slot["id"]}/delete'
    delete_job = f'/api/employer/jobs/{job["id"]}/delete'
    for path in (delete_slot, delete_job, '/api/auth/logout'):
        assert client.post(path, csrf=False).status_code == 403
        assert client.post(path, csrf=False, headers={'X-CSRF-Token': other_token}).status_code == 403

    state = client.get('/api/employer/bootstrap').json['state']
    assert [item['id'] for item in state['jobs']] == [str(job['id'])]
    assert [item['id'] for item in state['slots']] == [str(slot['id'])]
    for path in (delete_slot, delete_job, '/api/auth/logout'):
        assert client.post(path, csrf=False, headers={'X-CSRF-Token': own_token}).status_code == 200
    assert client.get('/api/auth/me').status_code == 401


def test_matchwork_renders_script_text_as_escaped_html():
    node = shutil.which('node')
    assert node, 'Install Node.js to run the Matchwork rendering tests (see INSTALL.md).'
    script = Path(__file__).with_name('rendering.cjs')
    result = subprocess.run([node, script], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr


def test_sql_metacharacters_remain_bound_values(people, monkeypatch):
    from recruiting import accounts, jobs
    from recruiting.db import get_db
    from recruiting.errors import DomainError
    import pytest
    payload = "x' or 1=1; drop table users;--"
    original = get_db()
    calls = []

    class RecordingConnection:
        def execute(self, sql, parameters=()):
            calls.append((sql, parameters))
            return original.execute(sql, parameters)

    monkeypatch.setattr(accounts, 'get_db', lambda: RecordingConnection())
    with pytest.raises(DomainError) as error:
        accounts.authenticate(payload, 'DemoPass123!')
    assert error.value.status == 401
    assert any(payload in params and payload not in sql for sql, params in calls)
    j = jobs.create_job(people['employer'], payload, payload, ['python'])
    assert jobs.job(people['candidate'], j['id'])['title'] == payload
    assert original.execute('SELECT count(*) FROM users').fetchone()[0] == 4
