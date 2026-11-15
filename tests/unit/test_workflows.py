import pytest


def test_job_crud_validation_and_dependent_deletion(people):
    from recruiting import jobs
    from recruiting.errors import DomainError
    e, c = people['employer'], people['candidate']
    for title, description in [('', 'Description'), ('Title', '  ')]:
        with pytest.raises(DomainError) as error:
            jobs.create_job(e, title, description, [])
        assert error.value.status == 400
    j = jobs.create_job(e, 'Engineer', 'Build products', ['Python'])
    jobs.update_job(e, j['id'], 'Developer', 'New description', [])
    assert jobs.job(e, j['id'])['title'] == 'Developer'
    assert jobs.job(e, j['id'])['skills'] == []
    jobs.delete_job(e, j['id'])
    with pytest.raises(DomainError) as error:
        jobs.job(e, j['id'])
    assert error.value.status == 404
    j = jobs.create_job(e, 'Engineer', 'Build products', ['Python'])
    jobs.apply(c, j['id'])
    with pytest.raises(DomainError) as error:
        jobs.delete_job(e, j['id'])
    assert error.value.status == 409
    assert len(jobs.applicants(e, j['id'])) == 1


def test_recommendations_fields_all_jobs_and_tie_breakers(people):
    from recruiting import jobs
    e, c = people['employer'], people['candidate']
    z = jobs.create_job(e, 'Zulu', 'Description Z', ['python'])
    a1 = jobs.create_job(e, 'alpha', 'Description A', ['sql'])
    a2 = jobs.create_job(e, 'Alpha', 'Description B', [])
    low = jobs.create_job(people['employer2'], 'Aardvark', 'Description C', ['rust'])
    result = jobs.recommendations(c)
    assert [j['id'] for j in result] == [a1['id'], a2['id'], z['id'], low['id']]
    assert [j['score'] for j in result] == [100, 100, 100, 0]
    assert result[0]['company_name'] == 'Northstar'
    assert result[0]['skills'] == ['sql']
    assert result[0]['description'] == 'Description A'


def test_applications_pending_duplicate_owner_and_statuses(people):
    from recruiting import jobs
    from recruiting.errors import DomainError
    from recruiting.db import get_db
    e, c = people['employer'], people['candidate']
    j = jobs.create_job(e, 'Engineer', 'Build products', ['python', 'sql'])
    a = jobs.apply(c, j['id'])
    assert a['status'] == 'Pending'
    assert a['title'] == 'Engineer' and a['company_name'] == 'Northstar'
    assert a['booking'] is None
    with pytest.raises(DomainError) as error:
        jobs.apply(c, j['id'])
    assert error.value.status == 409
    assert get_db().execute('SELECT count(*) FROM applications').fetchone()[0] == 1
    assert jobs.applications(people['candidate2']) == []
    for actor in [people['candidate2'], e]:
        with pytest.raises(DomainError) as error:
            jobs.application(actor, a['id'])
        assert error.value.status == 403
    for actor in [c, people['employer2']]:
        with pytest.raises(DomainError) as error:
            jobs.set_status(actor, a['id'], 'Accepted')
        assert error.value.status == 403
    for status in ['Interviewing', 'Rejected', 'Accepted', 'Pending']:
        jobs.set_status(e, a['id'], status)
        assert jobs.application(c, a['id'])['status'] == status
    with pytest.raises(DomainError) as error:
        jobs.set_status(e, a['id'], 'Hired')
    assert error.value.status == 400
    assert jobs.application(c, a['id'])['status'] == 'Pending'


def test_applicants_fields_and_both_tie_breakers(people):
    from recruiting import jobs
    from recruiting.accounts import register, update_profile
    e = people['employer']
    j = jobs.create_job(e, 'Engineer', 'Build products', ['python'])
    c1, c2 = people['candidate'], people['candidate2']
    c3 = register('third@example.test', 'DemoPass123!', 'Candidate', 'aaron')
    update_profile(c1, 'Zulu', ['python'], 'Secret resume')
    update_profile(c2, 'Aaron', ['python'], '')
    update_profile(c3, 'aaron', ['python'], '')
    for c in [c1, c2, c3]:
        jobs.apply(c, j['id'])
    rows = jobs.applicants(e, j['id'])
    assert [a['candidate_id'] for a in rows] == [c2['id'], c3['id'], c1['id']]
    assert rows[0]['skills'] == ['python'] and rows[0]['score'] == 100
    assert rows[0]['display_name'] == 'Aaron'
    assert rows[0]['status'] == 'Pending' and rows[0]['booking'] is None
    assert all('resume' not in a and 'password_hash' not in a for a in rows)


def test_wrong_roles_ownership_and_missing_objects(people):
    from recruiting import jobs
    from recruiting.errors import DomainError
    e, c, other = people['employer'], people['candidate'], people['employer2']
    j = jobs.create_job(e, 'Engineer', 'Build products', [])
    denied = [
        lambda: jobs.create_job(c, 'No', 'No', []),
        lambda: jobs.update_job(other, j['id'], 'No', 'No', []),
        lambda: jobs.delete_job(other, j['id']),
        lambda: jobs.applicants(other, j['id']),
        lambda: jobs.apply(e, j['id']),
    ]
    for operation in denied:
        with pytest.raises(DomainError) as error:
            operation()
        assert error.value.status == 403
    for operation in [lambda: jobs.job(c, 999), lambda: jobs.application(c, 999),
                      lambda: jobs.applicants(e, 999), lambda: jobs.apply(c, 999)]:
        with pytest.raises(DomainError) as error:
            operation()
        assert error.value.status == 404
    with pytest.raises(DomainError) as error:
        jobs.recommendations(None)
    assert error.value.status == 401
