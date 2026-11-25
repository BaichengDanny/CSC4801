"""Verify actual authenticated API scores/order -> product frontend projection.

The legacy local-demo Python/JS calculation comparison is retained behind
--legacy-functions. Online pages do not call that calculator anymore.
"""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[2]
CASES=[{'candidate':['\u1c89'],'required':['\u1c8a'],'expected':0,'kind':'QA3-04'},
       {'candidate':['\ua7cb'],'required':['\u0264'],'expected':0,'kind':'QA3-04'}]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',default='output/qa3-04/api-frontend-contract.json')
    parser.add_argument('--unicode-only',action='store_true')
    parser.add_argument('--legacy-functions',action='store_true')
    args=parser.parse_args()
    if args.legacy_functions:
        return subprocess.run([sys.executable,str(ROOT/'tests/acceptance/legacy_matching_comparison.py'),
                               '--output',args.output],cwd=ROOT).returncode
    sys.path.insert(0,str(ROOT))
    from legacy_matching_comparison import dataset,SEED
    from recruiting import create_app,accounts,jobs
    from recruiting.db import migrate,get_db
    data=dataset()
    cases=CASES if args.unicode_only else data['cases']+CASES
    payload={'candidate':[],'employer':[],'jobs':[],'applicants':[]}
    failures=[]
    # In-memory relational fixture keeps the large corpus isolated and bounded.
    app=create_app({'TESTING':True,'DATABASE':':memory:','SECRET_KEY':'synthetic-api-contract',
                    'NOW':lambda:datetime(2030,1,1,9,tzinfo=timezone.utc)})
    with app.app_context():
        migrate()
        c=accounts.register('contract-c@example.test','DemoPass123!','Candidate','Contract Candidate')
        e=accounts.register('contract-e@example.test','DemoPass123!','Employer','Contract Employer')
        password_hash=get_db().execute('SELECT password_hash FROM users WHERE id=?',(e['id'],)).fetchone()[0]
        def login(actor):
            client=app.test_client()
            response=client.post('/api/auth/login',json={'email':actor['email'],'password':'DemoPass123!','role':actor['role']})
            assert response.status_code==200,response.json
            return client
        cc,ec=login(c),login(e)
        job=jobs.create_job(e,'Contract role','Description',[])
        jobs.apply(c,job['id'])
        for index,case in enumerate(cases):
            accounts.update_profile(c,'Contract Candidate',case['candidate'],'')
            jobs.update_job(e,job['id'],'Contract role','Description',case['required'])
            candidate=cc.get('/api/candidate/bootstrap')
            employer=ec.get('/api/employer/bootstrap')
            assert candidate.status_code==employer.status_code==200
            rows=candidate.json['jobs'];apps=employer.json['state']['applications']
            payload['candidate'].append(rows);payload['employer'].append(apps)
            if rows[0]['score']!=apps[0]['score'] or ('expected' in case and rows[0]['score']!=case['expected']):
                failures.append({'index':index,'input':case,'candidate':rows[0]['score'],'employer':apps[0]['score']})
            if 'pair' in case and not args.unicode_only:
                previous=payload['candidate'][case['pair']][0]['score']
                if rows[0]['score']!=previous:
                    failures.append({'index':index,'input':case,'reason':'metamorphic result changed'})
        # Real API fixtures for numeric-ID and Unicode text ordering.
        db=get_db()
        for group in data['jobGroups']:
            for table in ('applications','job_skills','jobs'): db.execute('DELETE FROM '+table)
            accounts.update_profile(c,'Contract Candidate',['a','b'],'')
            required={100:[],66:['a','b','c'],50:['a','c'],33:['a','c','d'],0:['z']}
            for row in group:
                identifier=int(row['id'])
                db.execute('INSERT INTO jobs(id,employer_id,title,description,created_at) VALUES (?,?,?,?,?)',
                           (identifier,e['id'],row['title'],'Description',1))
                db.executemany('INSERT INTO job_skills VALUES (?,?)',[(identifier,s) for s in required[row['match']]])
            rows=cc.get('/api/candidate/bootstrap').json['jobs']
            expected=[row['id'] for row in sorted(group,key=lambda r:(-r['match'],r['title'].lower(),int(r['id'])))]
            assert [row['id'] for row in rows]==expected
            payload['jobs'].append(rows)
        for group in data['applicantGroups']:
            for table in ('auth_sessions','bookings','slots','applications','job_skills','jobs',
                          'candidate_skills','candidate_profiles','companies','users'):
                db.execute('DELETE FROM '+table)
            db.execute('INSERT INTO users(id,email,password_hash,role,display_name) VALUES (?,?,?,?,?)',
                       (3,'owner@example.test',password_hash,'Employer','Owner'))
            db.execute('INSERT INTO companies(employer_id,name) VALUES (?,?)',(3,'Company'))
            owner=accounts.user(3); ec=login(owner)
            posting=jobs.create_job(owner,'Applicants','Description',['a','b','c','d','e','f'])
            skills={0:['z'],33:['a','b'],50:['a','b','c'],66:['a','b','c','d'],100:['a','b','c','d','e','f']}
            for row in group:
                identifier=int(row['candidateId'])
                db.execute('INSERT INTO users(id,email,password_hash,role,display_name) VALUES (?,?,?,?,?)',
                           (identifier,'c'+str(identifier)+'@example.test',password_hash,'Candidate',row['name']))
                db.execute('INSERT INTO candidate_profiles(user_id) VALUES (?)',(identifier,))
                actor=accounts.user(identifier)
                accounts.update_profile(actor,row['name'],skills[row['match']],'')
                jobs.apply(actor,posting['id'])
            rows=ec.get('/api/employer/bootstrap').json['state']['applications']
            expected=[row['candidateId'] for row in sorted(group,key=lambda r:(-r['match'],r['name'].lower(),int(r['candidateId'])))]
            assert [row['candidateId'] for row in rows]==expected
            payload['applicants'].append(rows)
    result=subprocess.run([shutil.which('node') or 'node',str(ROOT/'tests/frontend/server_bridge.cjs')],
                          input=json.dumps(payload,ensure_ascii=True),capture_output=True,text=True,
                          encoding='utf-8',check=True,timeout=30)
    frontend=json.loads(result.stdout)
    for key,groups in payload.items():
        for index,rows in enumerate(groups):
            expected=[{'id':r['id'],'match':r['score'],'rank':r['rank'],
                       **({'candidateId':r['candidateId']} if 'candidateId' in r else {})} for r in rows]
            if frontend[key][index]!=expected:
                failures.append({'group':key,'index':index,'expected':expected,'actual':frontend[key][index]})
    report={'architecture':'authoritative API -> actual product frontend projection',
            'seed':SEED,'score_cases':len(cases),'job_sort_groups':len(payload['jobs']),
            'applicant_sort_groups':len(payload['applicants']),'failures':failures,
            'unicode_results':[{'input':case,'api_score':payload['candidate'][index][0]['score'],
                                'frontend_score':frontend['candidate'][index][0]['match']}
                               for index,case in enumerate(cases) if case.get('kind')=='QA3-04'],
            'inputs':cases}
    destination=ROOT/args.output;destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_text(json.dumps(report,ensure_ascii=True,indent=2),encoding='utf-8')
    print(json.dumps({key:value for key,value in report.items() if key not in ('inputs','failures')}))
    print('Failures:',len(failures))
    for failure in failures[:5]: print(json.dumps(failure,ensure_ascii=True))
    return 1 if failures else 0

if __name__=='__main__':sys.exit(main())
