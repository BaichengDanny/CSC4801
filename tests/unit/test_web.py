def login(client, email='alex@example.test', role='Candidate'):
    return client.post('/api/auth/login', json={'email': email, 'password': 'DemoPass123!', 'role': role})


def test_registration_and_session_lifecycle(app):
    client = app.test_client()
    response = client.post('/api/auth/register', json={
        'email': 'new@example.test', 'password': 'DemoPass123!', 'role': 'Candidate', 'name': 'New Person',
    })
    assert response.status_code == 201
    assert client.get('/api/candidate/bootstrap').status_code == 200
    cookie = client.get_cookie('session').value
    assert client.post('/api/auth/logout').status_code == 200
    assert client.get('/api/candidate/bootstrap').status_code == 401
    client.set_cookie('session', cookie)
    assert client.get('/api/candidate/bootstrap').status_code == 401


def test_auth_errors_and_role_boundaries(app, people):
    client = app.test_client()
    assert client.get('/api/candidate/bootstrap').status_code == 401
    assert client.post('/api/candidate/applications', json={'jobId': 1}).status_code == 401
    assert client.post('/api/auth/login', json={
        'email': 'alex@example.test', 'password': 'wrong-password', 'role': 'Candidate',
    }).status_code == 401
    assert login(client).status_code == 200
    assert client.post('/api/employer/jobs', json={'title': 'Role', 'body': 'Work'}).status_code == 403
    assert client.post('/api/candidate/applications', json={'jobId': 999}).status_code == 404
    assert client.post('/api/auth/logout').status_code == 200
    assert client.post('/api/auth/logout').status_code == 401


def test_resume_stays_private_and_user_text_is_json(app, people):
    from recruiting.accounts import update_profile, update_company
    from recruiting.jobs import create_job
    visible = '<script>alert(1)</script>'
    private = '<script>alert(2)</script>'
    c, e = people['candidate'], people['employer']
    update_profile(c, visible, ['Python'], private)
    update_company(e, visible, visible)
    create_job(e, visible, visible, [visible])
    client = app.test_client()
    login(client)
    own = client.get('/api/candidate/bootstrap')
    assert own.status_code == 200 and own.mimetype == 'application/json'
    profile = own.get_json()['state']['profile']
    assert profile['name'] == visible and profile['resume'] == private
    assert not own.get_data(as_text=True).lstrip().startswith('<')
    shell = client.get('/candidate/dashboard')
    assert shell.status_code == 200 and private not in shell.get_data(as_text=True)
    other = app.test_client()
    login(other, 'blair@example.test')
    assert private not in other.get('/api/candidate/bootstrap').get_data(as_text=True)
    employer = app.test_client()
    login(employer, 'north@example.test', 'Employer')
    employer_body = employer.get('/api/employer/bootstrap').get_json()
    assert private not in employer.get('/api/employer/bootstrap').get_data(as_text=True)
    assert employer_body['state']['jobs'][0]['title'] == visible


def test_candidate_and_employer_api_browser_workflow(app, people):
    employer = app.test_client()
    login(employer, 'north@example.test', 'Employer')
    created = employer.post('/api/employer/jobs', json={
        'title': 'Backend Engineer', 'body': 'Build reliable services.', 'skills': ['Python', 'SQL'],
    })
    assert created.status_code == 201
    job_id = int(created.get_json()['job']['id'])
    candidate = app.test_client()
    login(candidate)
    applied = candidate.post('/api/candidate/applications', json={'jobId': job_id})
    assert applied.status_code == 201
    application = applied.get_json()['application']
    assert application['status'] == 'Pending'
    status = employer.post(f'/api/employer/applications/{application["id"]}/status', json={'status': 'Interviewing'})
    assert status.status_code == 200
    slot = employer.post('/api/employer/slots', json={
        'start': '2030-01-02T10:00:00+00:00', 'end': '2030-01-02T10:30:00+00:00',
    })
    assert slot.status_code == 201
    booked = candidate.post(
        f'/api/candidate/applications/{application["id"]}/book',
        json={'slotId': slot.get_json()['slot']['id']},
    )
    assert booked.status_code == 200
    assert booked.get_json()['application']['slotId'] == slot.get_json()['slot']['id']
    employer_apps = employer.get('/api/employer/bootstrap').get_json()['state']['applications']
    assert any(item['id'] == application['id'] and item['slotId'] for item in employer_apps)


def test_malformed_booking_and_other_application_access(app, people):
    from recruiting import jobs
    j = jobs.create_job(people['employer'], 'Engineer', 'Description', [])
    a = jobs.apply(people['candidate'], j['id'])
    client = app.test_client()
    login(client, 'blair@example.test')
    assert client.post(f'/api/candidate/applications/{a["id"]}/book', json={'slotId': 'abc'}).status_code == 403
    owner = app.test_client()
    login(owner)
    assert owner.post(f'/api/candidate/applications/{a["id"]}/book', json={'slotId': 'abc'}).status_code == 404
    assert client.post('/api/candidate/profile', json={'name': ''}).status_code == 400


def test_other_employer_cannot_manage_a_job(app, people):
    from recruiting import jobs
    j = jobs.create_job(people['employer'], 'Engineer', 'Description', [])
    client = app.test_client()
    login(client, 'field@example.test', 'Employer')
    assert client.post(f'/api/employer/jobs/{j["id"]}', json={'title': 'Taken', 'body': 'Nope'}).status_code == 403
    assert client.post(f'/api/employer/jobs/{j["id"]}/delete').status_code == 403
    titles = [item['title'] for item in client.get('/api/employer/bootstrap').get_json()['state']['jobs']]
    assert 'Engineer' not in titles
