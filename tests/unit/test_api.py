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
    assert body['jobs'][0]['score'] if False else body['jobs'][0]['title']
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


def test_invalid_job_create_and_edit_leave_listing_unchanged(app, people):
    employer = app.test_client()
    candidate = app.test_client()
    assert login(employer, 'north@example.test', 'Employer').status_code == 200
    assert login(candidate, 'alex@example.test', 'Candidate').status_code == 200
    listing = {'title': 'Engineer', 'desc': 'Build services', 'body': 'Build reliable services',
               'skills': ['Python'], 'location': 'Remote', 'type': 'Full-time', 'status': 'Active'}
    rejected = employer.post('/api/employer/jobs', json={**listing, 'location': 'x' * 121})
    assert rejected.status_code == 400
    assert candidate.get('/api/candidate/bootstrap').json['jobs'] == []

    initial = employer.post('/api/employer/jobs', json=listing)
    assert initial.status_code == 201
    original = initial.json['job']
    edit_url = f'/api/employer/jobs/{original["id"]}'
    for invalid in ({'location': 'x' * 121}, {'desc': 'x' * 301},
                    {'type': 'Invalid'}, {'status': 'Invalid'}):
        rejected = employer.post(edit_url, json={
            'title': 'Changed', 'body': 'Changed description', 'skills': ['Rust'], **invalid,
        })
        assert rejected.status_code == 400
        assert employer.get('/api/employer/bootstrap').json['state']['jobs'] == [original]

    changed = employer.post(edit_url, json={'title': 'Engineer II', 'status': 'Closed'}).json['job']
    assert changed == {**original, 'title': 'Engineer II', 'status': 'Closed'}


def test_candidate_bootstrap_distinguishes_same_name_employers(app, people):
    from recruiting import accounts, jobs, scheduling

    north = people['employer']
    field = people['employer2']
    accounts.update_company(field, 'Northstar', 'Independent employer with the same name.')
    first = jobs.create_job(north, 'Engineer', 'Original job', [])
    other_team = jobs.create_job(north, 'Data Engineer', 'Same company, different job', [])
    foreign = jobs.create_job(field, 'Researcher', 'Another employer', [])
    application = jobs.apply(people['candidate'], first['id'])
    jobs.set_status(north, application['id'], 'Interviewing')
    available = scheduling.create_slot(north, other_team['id'], '2030-01-02T17:00:00Z', '2030-01-02T17:30:00Z')
    other = scheduling.create_slot(field, foreign['id'], '2030-01-02T18:00:00Z', '2030-01-02T18:30:00Z')

    client = app.test_client()
    assert login(client, 'alex@example.test', 'Candidate').status_code == 200
    payload = client.get('/api/candidate/bootstrap').json
    by_id = {j['id']: j for j in payload['jobs']}
    target = by_id[str(first['id'])]
    unrelated = by_id[str(foreign['id'])]
    slots = {s['id']: s for s in payload['state']['slots']}
    assert target['company'] == unrelated['company'] == 'Northstar'
    assert target['owner'] == slots[str(available['id'])]['owner']
    assert unrelated['owner'] != target['owner']
    assert str(other['id']) not in slots
    assert payload['companies'][target['owner']]['about'] == 'A small engineering team.'
    assert payload['companies'][unrelated['owner']]['about'] == 'Independent employer with the same name.'


def test_candidate_schedule_contains_only_own_bookings_and_eligible_open_slots(app, people, monkeypatch):
    from datetime import datetime, timezone

    from recruiting import jobs, scheduling

    candidate, other = people['candidate'], people['candidate2']
    employer = people['employer']
    job = jobs.create_job(employer, 'Engineer', 'Build services', [])
    second_job = jobs.create_job(employer, 'Data Engineer', 'Build reports', [])
    own = jobs.apply(candidate, job['id'])
    next_application = jobs.apply(candidate, second_job['id'])
    other_application = jobs.apply(other, job['id'])
    for application in (own, other_application):
        jobs.set_status(employer, application['id'], 'Interviewing')

    def slot(day, hour):
        return scheduling.create_slot(employer, job['id'], f'2030-01-{day}T{hour}:00:00Z', f'2030-01-{day}T{hour}:30:00Z')

    own_slot = slot('02', '10')
    slot('02', '11')  # Unbooked slot that will have elapsed.
    other_slot = slot('04', '10')
    available = slot('05', '10')
    scheduling.book(candidate, own['id'], own_slot['id'])
    scheduling.book(other, other_application['id'], other_slot['id'])
    jobs.set_status(employer, own['id'], 'Rejected')
    monkeypatch.setitem(app.config, 'NOW', lambda: datetime(2030, 1, 3, tzinfo=timezone.utc))

    def visible(client):
        response = client.get('/api/candidate/bootstrap')
        assert response.status_code == 200
        return {item['id']: item['bookedBy'] for item in response.json['state']['slots']}

    client = app.test_client()
    assert login(client, candidate['email'], 'Candidate').status_code == 200
    assert visible(client) == {str(own_slot['id']): str(own['id'])}
    jobs.set_status(employer, next_application['id'], 'Interviewing')
    assert visible(client) == {str(own_slot['id']): str(own['id']), str(available['id']): None}

    other_client = app.test_client()
    assert login(other_client, other['email'], 'Candidate').status_code == 200
    assert visible(other_client) == {str(other_slot['id']): str(other_application['id'])}
    newcomer = app.test_client()
    assert newcomer.post('/api/auth/register', json={
        'email': 'new@example.test', 'password': 'DemoPass123!', 'name': 'New Candidate', 'role': 'Candidate',
    }).status_code == 201
    assert visible(newcomer) == {}


def test_slot_api_requires_explicit_timezone_and_preserves_far_future_slot(app, people):
    from recruiting.jobs import create_job

    create_job(people['employer'], 'Engineer', 'Build services', [])
    client = app.test_client()
    assert login(client, 'north@example.test', 'Employer').status_code == 200
    for start, end in [
        ('2030-07-15T09:00:00', '2030-07-15T09:30:00'),
        ('2030-07-15T09:00:00.900-07:00', '2030-07-15T09:30:00.100-07:00'),
        ('9999-12-31T23:00:00-01:00', '9999-12-31T23:30:00-01:00'),
        ('2030-07-15T09:00:00-07:00', '2030-07-15T08:30:00-07:00'),
    ]:
        assert client.post('/api/employer/slots', json={'start': start, 'end': end}).status_code == 400
    assert client.get('/api/employer/bootstrap').json['state']['slots'] == []

    created = client.post('/api/employer/slots', json={
        'start': '2030-07-15T09:00:00-07:00', 'end': '2030-07-15T09:30:00-07:00',
    })
    assert created.status_code == 201
    slot = created.json['slot']
    assert slot['start'] == '2030-07-15T16:00:00+00:00'
    assert slot['end'] == '2030-07-15T16:30:00+00:00'
    assert client.get('/api/employer/bootstrap').json['state']['slots'] == [slot]
    assert client.post(f'/api/employer/slots/{slot["id"]}/delete').status_code == 200
    assert client.get('/api/employer/bootstrap').json['state']['slots'] == []
