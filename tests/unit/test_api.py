def login(client, email, role):
    return client.post('/api/auth/login', json={'email': email, 'password': 'DemoPass123!', 'role': role})


def test_sign_in_page_and_static_files_are_served(app):
    client = app.test_client()
    page = client.get('/sign-in')
    assert page.status_code == 200
    assert b'Sign in' in page.data
    assert b'/api/auth/login' in page.data
    script = client.get('/candidate/assets/matchwork.js')
    assert script.status_code == 200
    assert b'/api/candidate/bootstrap' in script.data
    assert client.get('/shared/match.js').status_code == 200
    assert client.get('/candidate/dashboard').status_code == 200
    assert client.get('/recruiter/jobs').status_code == 200
    assert client.get('/candidate/../recruiting/accounts.py').status_code == 404
    assert client.get('/shared/../../.env.example').status_code == 404


def test_api_register_starts_a_session(app):
    client = app.test_client()
    page = client.get('/sign-in')
    assert b'/api/auth/register' in page.data
    assert b'href="/register"' not in page.data
    created = client.post('/api/auth/register', json={
        'email': ' New.Person@example.test ', 'password': 'DemoPass123!', 'role': 'Candidate', 'name': 'New Person',
    })
    assert created.status_code == 201
    payload = created.get_json()
    assert payload['role'] == 'Candidate' and 'password' not in payload and 'password_hash' not in payload
    assert client.get('/api/auth/me').get_json()['email'] == 'new.person@example.test'
    assert client.post('/api/auth/register', json={
        'email': 'new.person@example.test', 'password': 'DemoPass123!', 'role': 'Candidate', 'name': 'New Person',
    }).status_code == 409
    assert client.post('/api/auth/register', json={
        'email': 'short@example.test', 'password': 'short', 'role': 'Candidate', 'name': 'Short',
    }).status_code == 400
    employer = client.post('/api/auth/register', json={
        'email': 'jordan@example.test', 'password': 'DemoPass123!', 'role': 'Employer',
        'name': 'Jordan Lee', 'company': 'New Studio',
    })
    assert employer.status_code == 201
    assert client.get('/api/employer/bootstrap').get_json()['state']['company']['name'] == 'New Studio'


def test_api_login_role_and_logout(app, people):
    client = app.test_client()
    assert client.get('/api/candidate/bootstrap').status_code == 401
    assert login(client, 'alex@example.test', 'Employer').status_code == 403
    assert client.get('/api/auth/me').status_code == 401
    assert login(client, 'alex@example.test', 'Candidate').status_code == 200
    me = client.get('/api/auth/me')
    assert me.status_code == 200 and me.get_json()['role'] == 'Candidate'
    assert client.get('/api/employer/bootstrap').status_code == 403
    assert client.post('/api/auth/logout').status_code == 200
    assert client.get('/api/auth/me').status_code == 401


def test_candidate_and_employer_api_workflow(app, people):
    client = app.test_client()
    assert login(client, 'north@example.test', 'Employer').status_code == 200
    created = client.post('/api/employer/jobs', json={
        'title': "Engineer' OR 1=1 --",
        'desc': 'Build services',
        'body': 'Build services\n- Write SQL safely',
        'skills': ['Python', ' SQL '],
        'location': 'Remote',
        'type': 'Full-time',
        'status': 'Active',
    })
    assert created.status_code == 201
    job = created.get_json()['job']
    assert job['title'] == "Engineer' OR 1=1 --"
    assert job['skills'] == ['python', 'sql']
    assert job['location'] == 'Remote'
    script = client.post('/api/employer/jobs', json={
        'title': '<script>alert(1)</script>', 'desc': 'Description', 'skills': [],
    })
    assert script.status_code == 201
    assert script.is_json
    open_job = script.get_json()['job']
    assert open_job['title'] == '<script>alert(1)</script>'
    closed = client.post(f'/api/employer/jobs/{job["id"]}', json={'status': 'Closed'})
    assert closed.status_code == 200
    assert closed.get_json()['job']['status'] == 'Closed'
    assert closed.get_json()['job']['title'] == job['title']
    slot = client.post('/api/employer/slots', json={
        'start': '2030-01-02T18:00:00.000Z', 'end': '2030-01-02T18:30:00.000Z',
    })
    assert slot.status_code == 201, slot.get_json()
    overlap = client.post('/api/employer/slots', json={
        'start': '2030-01-02T18:15:00Z', 'end': '2030-01-02T18:45:00Z',
    })
    assert overlap.status_code == 409
    company = client.post('/api/employer/company', json={'name': 'Northstar Studio', 'about': 'A small team.', 'location': 'Oakland'})
    assert company.status_code == 200
    assert company.get_json()['company']['location'] == 'Oakland'
    assert client.post('/api/auth/logout').status_code == 200

    assert login(client, 'alex@example.test', 'Candidate').status_code == 200
    profile = client.post('/api/candidate/profile', json={'name': 'Alex Morgan', 'skills': ['Python'], 'resume': 'Private resume'})
    assert profile.status_code == 200
    boot = client.get('/api/candidate/bootstrap')
    assert boot.status_code == 200
    body = boot.get_json()
    assert body['state']['profile']['resume'] == 'Private resume'
    # Empty requirements score 100; Python matches one of two required skills.
    assert [item['id'] for item in body['jobs']] == [open_job['id'], job['id']]
    from recruiting import accounts, jobs
    rows = jobs.recommendations(accounts.user(people['candidate']['id']))
    assert [(str(row['id']), row['score']) for row in rows] == [
        (open_job['id'], 100), (job['id'], 50)]
    titles = [item['title'] for item in body['jobs']]
    assert "Engineer' OR 1=1 --" in titles
    assert '<script>alert(1)</script>' in titles
    refused = client.post('/api/candidate/applications', json={'jobId': job['id']})
    assert refused.status_code == 409
    applied = client.post('/api/candidate/applications', json={'jobId': open_job['id']})
    assert applied.status_code == 201
    assert applied.get_json()['application']['status'] == 'Pending'
    duplicate = client.post('/api/candidate/applications', json={'jobId': open_job['id']})
    assert duplicate.status_code == 409
    assert client.post('/api/auth/logout').status_code == 200

    assert login(client, 'north@example.test', 'Employer').status_code == 200
    employer = client.get('/api/employer/bootstrap').get_json()
    assert 'Private resume' not in client.get('/api/employer/bootstrap').get_data(as_text=True)
    application_id = employer['state']['applications'][0]['id']
    status = client.post(f'/api/employer/applications/{application_id}/status', json={'status': 'Interviewing'})
    assert status.status_code == 200
    blocked = client.post(f'/api/employer/jobs/{job["id"]}/delete')
    assert blocked.status_code == 409
    assert client.post('/api/auth/logout').status_code == 200

    assert login(client, 'field@example.test', 'Employer').status_code == 200
    assert client.post(f'/api/employer/applications/{application_id}/status', json={'status': 'Accepted'}).status_code == 403
    assert client.post(f'/api/employer/jobs/{job["id"]}/delete').status_code == 403
    assert client.post('/api/auth/logout').status_code == 200

    assert login(client, 'alex@example.test', 'Candidate').status_code == 200
    candidate = client.get('/api/candidate/bootstrap').get_json()
    application = next(item for item in candidate['state']['applications'] if item['jobId'] == open_job['id'])
    slot_id = candidate['state']['slots'][0]['id']
    booked = client.post(f'/api/candidate/applications/{application["id"]}/book', json={'slotId': slot_id})
    assert booked.status_code == 200, booked.get_json()
    assert booked.get_json()['application']['slotId'] == slot_id
    again = client.post(f'/api/candidate/applications/{application["id"]}/book', json={'slotId': slot_id})
    assert again.status_code == 409
    assert again.get_json()['message']
    assert client.post('/api/auth/logout').status_code == 200

    blair = app.test_client()
    assert login(blair, 'blair@example.test', 'Candidate').status_code == 200
    stolen = blair.post(f'/api/candidate/applications/{application["id"]}/book', json={'slotId': 'abc'})
    assert stolen.status_code == 403
