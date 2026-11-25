"""Run a small HTTP acceptance check against the local demo Docker environment."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from http.cookiejar import CookieJar
import json
from threading import Barrier
import time
from urllib.error import HTTPError
from urllib.parse import urljoin
from urllib.request import HTTPCookieProcessor, ProxyHandler, Request, build_opener


class Session:
    def __init__(self, base):
        self.base = base.rstrip('/') + '/'
        self.opener = build_opener(ProxyHandler({}), HTTPCookieProcessor(CookieJar()))

    def request(self, path, data=None):
        request = Request(urljoin(self.base, path.lstrip('/')),
                          data=None if data is None else json.dumps(data).encode(),
                          headers={'Content-Type': 'application/json'})
        try:
            response = self.opener.open(request, timeout=20)
        except HTTPError as error:
            response = error
        with response:
            raw = response.read().decode()
            return response.status, json.loads(raw)

    def post(self, path, data, expected=200):
        status, payload = self.request(path, data)
        assert status == expected, (path, status, payload)
        return payload


def main(base):
    run = str(time.time_ns())
    checks = []
    employer = Session(base)
    candidates = [Session(base), Session(base)]
    stranger = Session(base)
    for index, (session, role) in enumerate(
            [(employer, 'Employer'), (candidates[0], 'Candidate'),
             (candidates[1], 'Candidate'), (stranger, 'Employer')]):
        session.post('/api/auth/register', {
            'email': f'qa-http-{run}-{index}@example.test',
            'password': 'DemoPass123!', 'role': role, 'name': f'QA HTTP {index}',
        }, 201)
    private = f'QA private resume {run}'
    candidates[0].post('/api/candidate/profile', {'resume': private, 'skills': ['Python', 'SQL']})
    assert private not in json.dumps(candidates[1].request('/api/candidate/bootstrap')[1])
    assert private not in json.dumps(employer.request('/api/employer/bootstrap')[1])
    checks.append('resume-private-across-accounts')
    job = employer.post('/api/employer/jobs', {
        'title': "QA engineer ' OR 1=1 --", 'body': 'Local HTTP acceptance', 'skills': ['Python', 'SQL'],
    }, 201)['job']
    assert job['title'] == "QA engineer ' OR 1=1 --"
    applications = [
        candidate.post('/api/candidate/applications', {'jobId': job['id']}, 201)['application']
        for candidate in candidates
    ]
    assert all(application['status'] == 'Pending' for application in applications)
    candidates[0].post('/api/candidate/applications', {'jobId': job['id']}, 409)
    checks.append('pending-and-duplicate-application')
    stranger.post('/api/employer/jobs/' + job['id'] + '/delete', {}, 403)
    candidates[0].post('/api/employer/jobs', {'title': 'Forbidden', 'body': 'Forbidden'}, 403)
    assert Session(base).request('/api/candidate/bootstrap')[0] == 401
    candidates[0].post('/api/candidate/applications', {'jobId': 9223372036854775807}, 404)
    checks.append('401-403-404-and-owner-boundaries')
    for application in applications:
        employer.post('/api/employer/applications/' + application['id'] + '/status',
                      {'status': 'Interviewing'})
    start = (datetime.now(timezone.utc) + timedelta(days=3)).replace(
        hour=10, minute=0, second=0, microsecond=0)
    slot = employer.post('/api/employer/slots', {
        'start': start.isoformat(), 'end': (start + timedelta(minutes=30)).isoformat(),
    }, 201)['slot']
    candidates[1].post('/api/candidate/applications/' + applications[0]['id'] + '/book',
                       {'slotId': slot['id']}, 403)
    barrier = Barrier(2)

    def attempt(index):
        barrier.wait(timeout=10)
        return candidates[index].request(
            '/api/candidate/applications/' + applications[index]['id'] + '/book',
            {'slotId': slot['id']})

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(attempt, range(2)))
    assert sorted(status for status, _ in outcomes) == [200, 409], outcomes
    loser = next(payload for status, payload in outcomes if status == 409)
    assert loser['message'] == 'Slot already booked'
    booked = [
        application for application in employer.request('/api/employer/bootstrap')[1]['state']['applications']
        if application['slotId'] == slot['id']
    ]
    assert len(booked) == 1
    checks.append('atomic-two-client-http-booking')
    employer.post('/api/employer/applications/' + booked[0]['id'] + '/status', {'status': 'Accepted'})
    after = employer.request('/api/employer/bootstrap')[1]['state']['applications']
    assert next(item for item in after if item['id'] == booked[0]['id'])['slotId'] == slot['id']
    employer.post('/api/employer/slots/' + slot['id'] + '/delete', {}, 409)
    employer.post('/api/employer/jobs/' + job['id'] + '/delete', {}, 409)
    checks.append('booking-preserved-and-dependent-deletion-rejected')
    print(json.dumps({'checks': checks, 'race_statuses': [status for status, _ in outcomes],
                      'slot_id': slot['id'], 'job_id': job['id'],
                      'booked_application_id': booked[0]['id']}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--base-url', default='http://127.0.0.1:8083')
    main(parser.parse_args().base_url)
