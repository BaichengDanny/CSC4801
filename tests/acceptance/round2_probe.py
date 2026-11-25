"""Reproducible, bounded input probe against an isolated synthetic Flask app.

--source can point to the saved pre-round-2 snapshot to reproduce the findings.
Every input and outcome is saved. Unexpected exceptions fail the run and retain
their traceback; they are never reclassified as an acceptable error response.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import random
import sys
import tempfile
import traceback

SEED = 48012026


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', default=str(Path(__file__).resolve().parents[2]))
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(Path(args.source).resolve()))
    from recruiting import create_app, accounts, jobs
    from recruiting.db import migrate, get_db
    rng = random.Random(SEED)
    cases = []
    # Minimal witnesses retained after reducing the original 1e400 and long
    # malformed bodies: true, 1.5, 1e309, null, and a single opening brace.
    for token in ('true','false','1.5','1.0','1e309','null','[]','{}','0','-1','9223372036854775808','"invalid"'):
        cases.append(('/api/candidate/applications','{"jobId":'+token+'}',404,'resource-id'))
    for raw in ('null','{','', '[]','true','"text"','{"name":'):
        cases.append(('/api/candidate/profile',raw,400,'json-object'))
    for index in range(40):
        value = rng.choice([None, True, rng.randrange(-20,20), {}, [['nested']]])
        cases.append(('/api/candidate/profile',json.dumps({'skills':value}),400,'skills-type'))
        month = rng.choice((0,13,99))
        data = {'start':'2030-'+str(month).zfill(2)+'-02T10:00:00Z',
                'end':'2030-01-02T10:30:00Z'}
        cases.append(('/api/employer/slots',json.dumps(data),400,'calendar'))
    results = []
    with tempfile.TemporaryDirectory(prefix='csc4801-round2-') as temporary:
        app = create_app({'TESTING':True,'DATABASE':str(Path(temporary)/'probe.sqlite3'),
                          'SECRET_KEY':'synthetic-probe-only',
                          'NOW':lambda:datetime(2030,1,1,9,tzinfo=timezone.utc)})
        with app.app_context():
            migrate()
            c = accounts.register('probe-c@example.test','DemoPass123!','Candidate','Probe Candidate')
            e = accounts.register('probe-e@example.test','DemoPass123!','Employer','Probe Employer')
            jobs.create_job(e,'Probe role','Description',[])
            clients = {}
            for actor in (c,e):
                client=app.test_client()
                assert client.post('/api/auth/login',json={
                    'email':actor['email'],'password':'DemoPass123!','role':actor['role']}).status_code == 200
                clients[actor['role']]=client
            db=get_db()
            def state():
                tables=('users','candidate_profiles','candidate_skills','companies','jobs',
                        'job_skills','applications','slots','bookings')
                return {t:[tuple(r) for r in db.execute('SELECT * FROM '+t+' ORDER BY 1')]
                        for t in tables}
            for index,(path,raw,expected,partition) in enumerate(cases):
                # Each case starts with no applications; this is an isolated test DB.
                db.execute('DELETE FROM applications')
                before=state()
                record={'index':index,'partition':partition,'path':path,'raw':raw,
                        'expected_status':expected}
                try:
                    response=clients['Employer' if '/employer/' in path else 'Candidate'].post(
                        path,data=raw,content_type='application/json')
                    record.update(actual_status=response.status_code,response=response.json,
                                  data_unchanged=state()==before)
                    record['passed']=response.status_code==expected and record['data_unchanged']
                except Exception as error:
                    record.update(passed=False,unexpected_exception=repr(error),
                                  traceback=traceback.format_exc(),data_unchanged=state()==before)
                results.append(record)
    report={'seed':SEED,'source':str(Path(args.source).resolve()),'cases':len(results),
            'passed':sum(r['passed'] for r in results),
            'failures':[r for r in results if not r['passed']],'results':results}
    destination=Path(args.output)
    destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('failures','results')}))
    for failure in report['failures']:
        print('FAIL',failure['index'],repr(failure['raw']),failure.get('actual_status'),
              failure.get('unexpected_exception',''),flush=True)
    return 1 if report['failures'] else 0


if __name__=='__main__':
    sys.exit(main())
