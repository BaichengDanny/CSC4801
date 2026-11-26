"""Spec regressions found during the 2026-11-24 acceptance review.

Run with: python -m pytest tests/unit/test_acceptance_regressions.py -q
These assertions cover request atomicity and explicit, renderable slot times.
"""
import pytest


def employer_client(app):
    client = app.test_client()
    response = client.post('/api/auth/login', json={
        'email': 'north@example.test',
        'password': 'DemoPass123!',
        'role': 'Employer',
    })
    assert response.status_code == 200
    return client


@pytest.mark.parametrize('invalid_fields', [
    {'type': 'Unsupported'},
    {'status': 'Unsupported'},
    {'desc': 'x' * 301},
])
def test_rejected_job_creation_preserves_database(app, people, invalid_fields):
    from recruiting.db import get_db

    client = employer_client(app)
    database = get_db()
    before = database.execute('SELECT count(*) FROM jobs').fetchone()[0]
    response = client.post('/api/employer/jobs', json={
        'title': 'QA rejected job',
        'body': 'A valid description',
        'skills': ['Python'],
        **invalid_fields,
    })
    assert response.status_code == 400
    assert database.execute('SELECT count(*) FROM jobs').fetchone()[0] == before


def test_rejected_job_edit_preserves_all_fields(app, people):
    from recruiting import jobs

    original = jobs.create_job(
        people['employer'], 'Original title', 'Original description', ['Python'])
    client = employer_client(app)
    response = client.post(f'/api/employer/jobs/{original["id"]}', json={
        'title': 'Changed despite rejection',
        'body': 'Changed description',
        'skills': ['Rust'],
        'status': 'Unsupported',
    })
    assert response.status_code == 400
    after = jobs.job(people['employer'], original['id'])
    assert (after['title'], after['description'], after['skills']) == (
        original['title'], original['description'], original['skills'])


def test_slot_api_requires_explicit_timezone(app, people):
    from recruiting import jobs
    from recruiting.db import get_db

    jobs.create_job(people['employer'], 'QA role', 'Description', [])
    client = employer_client(app)
    response = client.post('/api/employer/slots', json={
        'start': '2030-01-02T10:00:00',
        'end': '2030-01-02T10:30:00',
    })
    assert response.status_code == 400
    assert get_db().execute('SELECT count(*) FROM slots').fetchone()[0] == 0


def test_unrenderable_slot_is_rejected_without_server_error(app, people):
    from recruiting import jobs
    from recruiting.db import get_db

    jobs.create_job(people['employer'], 'QA role', 'Description', [])
    client = employer_client(app)
    response = client.post('/api/employer/slots', json={
        'start': '9999-12-31T23:00:00-23:59',
        'end': '9999-12-31T23:30:00-23:59',
    })
    assert response.status_code == 400
    assert get_db().execute('SELECT count(*) FROM slots').fetchone()[0] == 0
