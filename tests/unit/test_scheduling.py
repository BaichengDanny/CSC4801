import pytest


@pytest.fixture
def scenario(people):
    from recruiting import jobs, scheduling
    e, c = people['employer'], people['candidate']
    j = jobs.create_job(e, 'Engineer', 'Build products', ['python'])
    a = jobs.apply(c, j['id'])
    jobs.set_status(e, a['id'], 'Interviewing')
    s = scheduling.create_slot(e, j['id'], '2030-01-02T10:00:00+00:00', '2030-01-02T10:30:00+00:00')
    return j, a, s


def test_create_slot_timezone_and_delete(people):
    from recruiting import jobs, scheduling
    from recruiting.db import get_db
    e = people['employer']
    j = jobs.create_job(e, 'Engineer', 'Build products', [])
    s = scheduling.create_slot(e, j['id'], '2030-01-02T18:00:00+08:00', '2030-01-02T18:30:00+08:00')
    assert s['ends_at'] - s['starts_at'] == 1800
    assert scheduling.format_time(s['starts_at']) == '02 Jan 2030, 10:00 UTC'
    scheduling.delete_slot(e, s['id'])
    assert get_db().execute('SELECT count(*) FROM slots').fetchone()[0] == 0


@pytest.mark.parametrize(('start', 'end'), [
    ('2029-01-01T10:00:00+00:00', '2029-01-01T10:30:00+00:00'),
    ('2030-01-02T10:00:00+00:00', '2030-01-02T10:45:00+00:00'),
    ('2030-01-02T10:00:00+00:00', '2030-01-02T09:30:00+00:00'),
    ('2030-01-02T10:00:00', '2030-01-02T10:30:00'),
    ('not-a-date', 'not-a-date'),
])
def test_invalid_slots(people, start, end):
    from recruiting import jobs, scheduling
    from recruiting.errors import DomainError
    e = people['employer']
    j = jobs.create_job(e, 'Engineer', 'Build products', [])
    with pytest.raises(DomainError) as error:
        scheduling.create_slot(e, j['id'], start, end)
    assert error.value.status == 400


def test_booking_visible_preserved_and_deletion_rejected(people, scenario):
    from recruiting import jobs, scheduling
    from recruiting.errors import DomainError
    j, a, s = scenario
    c, e = people['candidate'], people['employer']
    assert [r['id'] for r in scheduling.available_slots(c, a['id'])] == [s['id']]
    scheduling.book(c, a['id'], s['id'])
    assert jobs.application(c, a['id'])['booking']['slot_id'] == s['id']
    assert jobs.applicants(e, j['id'])[0]['booking']['slot_id'] == s['id']
    assert scheduling.available_slots(c, a['id']) == []
    for status in ['Accepted', 'Rejected', 'Pending']:
        jobs.set_status(e, a['id'], status)
        assert jobs.application(c, a['id'])['booking']['slot_id'] == s['id']
    for operation in [lambda: scheduling.delete_slot(e, s['id']), lambda: jobs.delete_job(e, j['id'])]:
        with pytest.raises(DomainError) as error:
            operation()
        assert error.value.status == 409


def test_booking_conflict_contract(people, scenario):
    from recruiting import jobs, scheduling
    from recruiting.errors import DomainError
    from recruiting.db import get_db
    j, a, s = scenario
    other = jobs.apply(people['candidate2'], j['id'])
    jobs.set_status(people['employer'], other['id'], 'Interviewing')
    scheduling.book(people['candidate'], a['id'], s['id'])
    with pytest.raises(DomainError) as error:
        scheduling.book(people['candidate2'], other['id'], s['id'])
    assert (error.value.status, error.value.message) == (409, 'Slot already booked')
    assert get_db().execute('SELECT count(*) FROM bookings').fetchone()[0] == 1
    assert jobs.application(people['candidate2'], other['id'])['booking'] is None


def test_ineligible_bookings_leave_no_partial_changes(people, scenario, app):
    from recruiting import jobs, scheduling
    from recruiting.errors import DomainError
    from recruiting.db import get_db
    from datetime import datetime, timezone
    j, a, s = scenario
    c, e = people['candidate'], people['employer']
    for actor in [people['candidate2'], e]:
        with pytest.raises(DomainError) as error:
            scheduling.book(actor, a['id'], s['id'])
        assert error.value.status == 403
    foreign_job = jobs.create_job(people['employer2'], 'Elsewhere', 'Other job', [])
    foreign_slot = scheduling.create_slot(people['employer2'], foreign_job['id'],
                                         '2030-01-02T11:00:00Z', '2030-01-02T11:30:00Z')
    with pytest.raises(DomainError) as error:
        scheduling.book(c, a['id'], foreign_slot['id'])
    assert error.value.status == 403
    jobs.set_status(e, a['id'], 'Pending')
    with pytest.raises(DomainError) as error:
        scheduling.book(c, a['id'], s['id'])
    assert error.value.status == 409
    jobs.set_status(e, a['id'], 'Interviewing')
    app.config['NOW'] = lambda: datetime(2031, 1, 1, tzinfo=timezone.utc)
    with pytest.raises(DomainError) as error:
        scheduling.book(c, a['id'], s['id'])
    assert error.value.status == 409
    assert get_db().execute('SELECT count(*) FROM bookings').fetchone()[0] == 0


def test_same_employer_cross_job_and_one_booking_per_application(people, scenario):
    from recruiting import jobs, scheduling
    from recruiting.errors import DomainError
    j, a, s = scenario
    c, e = people['candidate'], people['employer']
    j2 = jobs.create_job(e, 'Other team', 'Same employer', [])
    s2 = scheduling.create_slot(e, j2['id'], '2030-01-02T11:00:00Z', '2030-01-02T11:30:00Z')
    scheduling.book(c, a['id'], s2['id'])
    with pytest.raises(DomainError) as error:
        scheduling.book(c, a['id'], s['id'])
    assert error.value.status == 409
    assert jobs.application(c, a['id'])['booking']['slot_id'] == s2['id']


def test_slot_ownership_and_job_dependency(people, scenario):
    from recruiting import jobs, scheduling
    from recruiting.errors import DomainError
    j, a, s = scenario
    with pytest.raises(DomainError) as error:
        scheduling.delete_slot(people['employer2'], s['id'])
    assert error.value.status == 403
    j2 = jobs.create_job(people['employer'], 'Only slot', 'No applications', [])
    scheduling.create_slot(people['employer'], j2['id'], '2030-01-02T11:00:00Z', '2030-01-02T11:30:00Z')
    with pytest.raises(DomainError) as error:
        jobs.delete_job(people['employer'], j2['id'])
    assert error.value.status == 409
