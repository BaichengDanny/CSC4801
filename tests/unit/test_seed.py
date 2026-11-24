from tests.unit.test_web import login as form_login


def login(client):
    return form_login(client, 'alex@example.test', 'Candidate')


def test_seed_is_repeatable_and_covers_requirements(app):
    from recruiting.seed import seed_demo
    from recruiting.db import get_db
    from recruiting.accounts import authenticate
    from recruiting import jobs, scheduling
    from datetime import datetime, timezone
    at = datetime(2030, 1, 1, tzinfo=timezone.utc)
    snapshots = []
    for _ in range(2):
        seed_demo(at)
        db = get_db()
        snapshots.append([tuple(r) for r in db.execute('SELECT id, job_id, starts_at, ends_at FROM slots ORDER BY id')])
        assert db.execute("SELECT count(*) FROM users WHERE role = 'Candidate'").fetchone()[0] >= 2
        assert db.execute("SELECT count(*) FROM users WHERE role = 'Employer'").fetchone()[0] >= 2
        assert {r[0] for r in db.execute('SELECT DISTINCT status FROM applications')} == {'Pending','Interviewing','Rejected','Accepted'}
        scores = []
        for email in ['alex@example.test', 'blair@example.test', 'casey@example.test']:
            actor = authenticate(email, 'DemoPass123!')
            scores.append(next(j['score'] for j in jobs.recommendations(actor)
                                if j['title'] == 'Backend Engineer' and j['company_name'] == 'Northstar Studio'))
        assert scores == [100, 50, 0]
        alex = authenticate('alex@example.test', 'DemoPass123!')
        assert next(j['score'] for j in jobs.recommendations(alex) if j['title'] == 'Graduate Programme' and not j['skills']) == 100
        google = db.execute(
            "SELECT j.location, j.categories FROM jobs j JOIN companies c ON c.employer_id = j.employer_id "
            "WHERE c.name = 'Google' AND j.title = 'Software Engineer'").fetchone()
        assert google['location'] == 'Mountain View, CA'
        assert 'Software' in google['categories']
        assert db.execute('SELECT count(*) FROM jobs').fetchone()[0] == 43
        candidates = [authenticate(email, 'DemoPass123!') for email in ['alex@example.test', 'blair@example.test']]
        eligible = []
        for c in candidates:
            a = next(a for a in jobs.applications(c) if a['status'] == 'Interviewing')
            eligible.append({s['id'] for s in scheduling.available_slots(c, a['id'])})
        assert eligible[0] & eligible[1]
    assert snapshots[0] == snapshots[1]


def test_reset_invalidates_existing_sessions_and_requires_confirmation(app):
    from recruiting.seed import seed_demo
    seed_demo(app.config['NOW']())
    client = app.test_client()
    assert login(client).status_code == 200
    assert client.get('/api/auth/me').status_code == 200
    runner = app.test_cli_runner()
    refused = runner.invoke(args=['seed'])
    assert refused.exit_code != 0
    assert client.get('/api/auth/me').status_code == 200
    result = runner.invoke(args=['seed', '--yes', '--at', '2030-01-01T00:00:00+00:00'])
    assert result.exit_code == 0, result.output
    assert client.get('/api/auth/me').status_code == 401
