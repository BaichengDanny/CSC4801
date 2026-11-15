import re

import pytest


def token(client, path='/login'):
    response = client.get(path)
    match = re.search(r'name="csrf_token" value="([^"]+)"', response.get_data(as_text=True))
    assert match, response.get_data(as_text=True)
    return match.group(1)


def login(client, email='alex@example.test'):
    return client.post('/login', data={'email': email, 'password': 'DemoPass123!', 'csrf_token': token(client)})


def test_registration_and_session_lifecycle(app):
    client = app.test_client()
    response = client.post('/register', data={
        'email': 'new@example.test', 'password': 'DemoPass123!', 'role': 'Candidate',
        'display_name': 'New Person', 'csrf_token': token(client, '/register'),
    })
    assert response.status_code == 302
    assert client.get('/dashboard').status_code == 200
    cookie = client.get_cookie('session').value
    csrf = token(client, '/dashboard')
    assert client.post('/logout', data={'csrf_token': csrf}).status_code == 302
    assert client.get('/dashboard').status_code == 401
    client.set_cookie('session', cookie)
    assert client.get('/dashboard').status_code == 401


def test_auth_errors_and_csrf(app, people):
    client = app.test_client()
    assert client.get('/dashboard').status_code == 401
    assert client.post('/jobs/1/apply').status_code == 401
    assert client.post('/login', data={'email': 'alex@example.test', 'password': 'DemoPass123!'}).status_code == 400
    assert login(client).status_code == 302
    assert client.get('/jobs/new').status_code == 403
    assert client.get('/jobs/999').status_code == 404
    assert client.post('/logout', data={'csrf_token': 'bad'}).status_code == 400
    assert client.get('/dashboard').status_code == 200


def test_direct_resume_access_and_escaping(app, people):
    from recruiting.accounts import update_profile, update_company
    from recruiting.jobs import create_job
    payload = '<script>alert(1)</script>'
    c, e = people['candidate'], people['employer']
    update_profile(c, payload, ['Python'], payload)
    update_company(e, payload, payload)
    j = create_job(e, payload, payload, [payload])
    client = app.test_client()
    login(client)
    for path in ['/profile', f'/candidates/{c["id"]}/resume', '/dashboard', f'/jobs/{j["id"]}']:
        response = client.get(path)
        assert response.status_code == 200
        assert payload not in response.get_data(as_text=True)
        assert '&lt;script&gt;' in response.get_data(as_text=True)
    other = app.test_client()
    login(other, 'blair@example.test')
    path = f'/candidates/{c["id"]}/resume'
    assert other.get(path).status_code == 403
    assert other.post(path, data={'resume': 'stolen', 'csrf_token': token(other, '/profile')}).status_code == 403
    employer = app.test_client()
    login(employer, 'north@example.test')
    assert employer.get(path).status_code == 403
    assert employer.post(path, data={'resume': 'stolen', 'csrf_token': token(employer, '/profile')}).status_code == 403


def test_candidate_and_employer_browser_workflow(app, people):
    employer = app.test_client()
    login(employer, 'north@example.test')
    created = employer.post('/jobs/new', data={
        'title': 'Backend Engineer', 'description': 'Build reliable services.',
        'skills': 'Python, SQL', 'csrf_token': token(employer, '/jobs/new'),
    })
    assert created.status_code == 302
    job_path = created.headers['Location']
    job_id = int(job_path.rsplit('/', 1)[-1])
    candidate = app.test_client()
    login(candidate)
    applied = candidate.post(job_path + '/apply', data={'csrf_token': token(candidate, job_path)})
    assert applied.status_code == 302
    app_path = applied.headers['Location']
    application_id = int(app_path.rsplit('/', 1)[-1])
    assert 'Pending' in candidate.get('/applications').get_data(as_text=True)
    status = employer.post(f'/applications/{application_id}/status', data={
        'status': 'Interviewing', 'csrf_token': token(employer, job_path + '/applicants'),
    })
    assert status.status_code == 302
    slot = employer.post(job_path + '/slots', data={
        'start': '2030-01-02T10:00', 'end': '2030-01-02T10:30',
        'csrf_token': token(employer, '/schedule'),
    })
    assert slot.status_code == 302
    from recruiting.db import get_db
    slot_id = get_db().execute('SELECT id FROM slots WHERE job_id = ?', (job_id,)).fetchone()[0]
    booked = candidate.post(app_path + '/book', data={
        'slot_id': str(slot_id), 'csrf_token': token(candidate, app_path),
    })
    assert booked.status_code == 302
    assert '02 Jan 2030, 10:00 UTC' in candidate.get(app_path).get_data(as_text=True)
    assert '02 Jan 2030, 10:00 UTC' in employer.get(job_path + '/applicants').get_data(as_text=True)


def test_malformed_forms_and_other_application_access(app, people):
    from recruiting import jobs
    j = jobs.create_job(people['employer'], 'Engineer', 'Description', [])
    a = jobs.apply(people['candidate'], j['id'])
    client = app.test_client()
    login(client, 'blair@example.test')
    assert client.get(f'/applications/{a["id"]}').status_code == 403
    assert client.post(f'/applications/{a["id"]}/book', data={
        'slot_id': 'abc', 'csrf_token': token(client, '/dashboard'),
    }).status_code == 403
    owner = app.test_client()
    login(owner)
    assert owner.post(f'/applications/{a["id"]}/book', data={
        'slot_id': 'abc', 'csrf_token': token(owner, '/dashboard'),
    }).status_code == 400
    assert client.post('/profile', data={
        'display_name': '', 'skills': '', 'resume': '', 'csrf_token': token(client, '/profile'),
    }).status_code == 400


def test_other_employer_direct_requests(app, people):
    from recruiting import jobs
    j = jobs.create_job(people['employer'], 'Engineer', 'Description', [])
    client = app.test_client()
    login(client, 'field@example.test')
    for path in [f'/jobs/{j["id"]}/edit', f'/jobs/{j["id"]}/applicants']:
        assert client.get(path).status_code == 403
    assert client.post(f'/jobs/{j["id"]}/delete', data={'csrf_token': token(client, '/dashboard')}).status_code == 403
