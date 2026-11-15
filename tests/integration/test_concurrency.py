from concurrent.futures import ThreadPoolExecutor
from threading import Barrier


def test_two_candidates_race_for_one_slot(app, people):
    from recruiting import jobs, scheduling
    from recruiting.db import get_db
    from recruiting.errors import DomainError
    e = people['employer']
    j = jobs.create_job(e, 'Engineer', 'Build products', [])
    candidates = [people['candidate'], people['candidate2']]
    applications = [jobs.apply(c, j['id']) for c in candidates]
    for a in applications:
        jobs.set_status(e, a['id'], 'Interviewing')
    slot = scheduling.create_slot(e, j['id'], '2030-01-02T10:00:00Z', '2030-01-02T10:30:00Z')
    barrier = Barrier(2)

    def attempt(pair):
        actor, application = pair
        with app.app_context():
            barrier.wait(timeout=10)
            try:
                scheduling.book(actor, application['id'], slot['id'])
                return 200, 'Booked'
            except DomainError as error:
                return error.status, error.message

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(attempt, zip(candidates, applications)))
    assert sorted(outcomes) == [(200, 'Booked'), (409, 'Slot already booked')]
    assert get_db().execute('SELECT count(*) FROM bookings').fetchone()[0] == 1
