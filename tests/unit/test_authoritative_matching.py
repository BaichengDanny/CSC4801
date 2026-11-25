"""QA3-04: the real JSON API is the score and ordering authority."""
import pytest

CASES=[('\u1c89','\u1c8a'),('\ua7cb','\u0264')]


def client_for(app,actor):
    client=app.test_client()
    assert client.post('/api/auth/login',json={
        'email':actor['email'],'password':'DemoPass123!','role':actor['role']}).status_code==200
    return client


def database_state():
    from recruiting.db import get_db
    return {table:[tuple(row) for row in get_db().execute('SELECT * FROM '+table+' ORDER BY 1')]
            for table in ('users','candidate_profiles','candidate_skills','jobs','job_skills',
                          'applications','slots','bookings')}


@pytest.mark.parametrize(('upper','lower'),CASES)
def test_unicode_scores_and_order_flow_through_real_api(app,people,upper,lower):
    from recruiting import accounts,jobs
    c,c2,e=people['candidate'],people['candidate2'],people['employer']
    accounts.update_profile(c,'SAME',[upper],'')
    accounts.update_profile(c2,'same',[lower],'')
    target=jobs.create_job(e,'Unicode role','Description',[lower])
    empty=jobs.create_job(e,'Empty role','Description',[])
    for actor in (c2,c): jobs.apply(actor,target['id'])
    cc,ec=client_for(app,c),client_for(app,e)
    payload=cc.get('/api/candidate/bootstrap').json
    assert [(row['id'],row['score'],row['rank']) for row in payload['jobs']]==[
        (str(empty['id']),100,0),(str(target['id']),0,1)]
    apps=ec.get('/api/employer/bootstrap').json['state']['applications']
    assert [(a['candidateId'],a['score'],a['rank']) for a in apps]==[
        (str(c2['id']),100,0),(str(c['id']),0,1)]
    assert all(a['jobId']==str(target['id']) for a in apps)
    # Editing the profile returns fresh complete results; same name/score uses stable ID.
    response=cc.post('/api/candidate/profile',json={'skills':[lower]})
    assert response.status_code==200
    snapshot=response.json['snapshot']
    assert next(j for j in snapshot['jobs'] if j['id']==str(target['id']))['score']==100
    assert [a['candidateId'] for a in ec.get('/api/employer/bootstrap').json['state']['applications']]==[
        str(c['id']),str(c2['id'])]
    # Editing required skills recomputes all applications in the write response.
    response=ec.post('/api/employer/jobs/'+str(target['id']),json={'skills':[upper]})
    assert response.status_code==200
    apps=response.json['snapshot']['state']['applications']
    assert [(a['candidateId'],a['score']) for a in apps]==[(str(c['id']),0),(str(c2['id']),0)]
    assert next(j for j in cc.get('/api/candidate/bootstrap').json['jobs']
                if j['id']==str(target['id']))['score']==0


def test_preview_is_read_only_and_uses_the_course_formula(app,people,monkeypatch):
    from recruiting import jobs
    e,c=people['employer'],people['candidate']
    one=jobs.create_job(e,'Third','Description',['Python','SQL','Rust'])
    empty=jobs.create_job(e,'Empty','Description',[])
    client=client_for(app,c)
    before=database_state()
    response=client.post('/api/candidate/matching-preview',json={'skills':['\ufeffPython',' PYTHON ','']})
    assert response.status_code==200
    assert [(j['id'],j['score'],j['rank']) for j in response.json['jobs']]==[
        (str(empty['id']),100,0),(str(one['id']),33,1)]
    assert {j['id']:j['baselineScore'] for j in response.json['jobs']}=={str(empty['id']):100,str(one['id']):66}
    assert database_state()==before
    for invalid in (None,True,'python',[None],['x'*81]):
        assert client.post('/api/candidate/matching-preview',json={'skills':invalid}).status_code==400
        assert database_state()==before


    # Deterministic interleaving: a job is deleted after draft rows are read.
    # Both preview values must use those captured requirements, not a second lookup.
    original = jobs.recommendations
    deleted = False
    def read_then_delete(actor, skills=None):
        nonlocal deleted
        rows = original(actor, skills=skills)
        if not deleted:
            jobs.delete_job(e, one['id'])
            deleted = True
        return rows
    monkeypatch.setattr(jobs, 'recommendations', read_then_delete)
    response = client.post('/api/candidate/matching-preview', json={'skills':['Python']})
    assert response.status_code == 200
    captured = next(row for row in response.json['jobs'] if row['id'] == str(one['id']))
    assert (captured['score'], captured['baselineScore']) == (33, 66)


def test_preview_and_ranked_results_keep_role_and_owner_boundaries(app,people):
    from recruiting import jobs
    own=jobs.create_job(people['employer'],'Own','Description',[])
    other=jobs.create_job(people['employer2'],'Other','Description',[])
    jobs.apply(people['candidate'],own['id'])
    jobs.apply(people['candidate2'],other['id'])
    anon=app.test_client()
    assert anon.post('/api/candidate/matching-preview',json={'skills':[]}).status_code==401
    for key in ('employer','employer2'):
        employer=client_for(app,people[key])
        assert employer.post('/api/candidate/matching-preview',json={'skills':[]}).status_code==403
        rows=employer.get('/api/employer/bootstrap').json['state']['applications']
        expected=own['id'] if key=='employer' else other['id']
        assert len(rows)==1 and rows[0]['jobId']==str(expected)
    candidate=client_for(app,people['candidate'])
    assert candidate.get('/api/employer/bootstrap').status_code==403


def test_api_title_ties_and_large_ids_are_authoritative(app,people):
    from recruiting import jobs
    from recruiting.db import get_db
    e=people['employer']
    low=jobs.create_job(e,'\u1c8a','Description',[])
    high=jobs.create_job(e,'\u1c89','Description',[])
    client=client_for(app,people['candidate'])
    rows=client.get('/api/candidate/bootstrap').json['jobs']
    assert [row['id'] for row in rows]==[str(high['id']),str(low['id'])]
    jobs.update_job(e,low['id'],'same','Description',[])
    jobs.update_job(e,high['id'],'SAME','Description',[])
    get_db().execute('UPDATE jobs SET id=? WHERE id=?',(9007199254740993,low['id']))
    get_db().execute('UPDATE jobs SET id=? WHERE id=?',(9007199254740992,high['id']))
    rows=client.get('/api/candidate/bootstrap').json['jobs']
    assert [(row['id'],row['score'],row['rank']) for row in rows]==[
        ('9007199254740992',100,0),('9007199254740993',100,1)]


def test_status_response_keeps_score_and_rank(app,people):
    from recruiting import jobs
    j=jobs.create_job(people['employer'],'Role','Description',['python','sql','rust'])
    a=jobs.apply(people['candidate'],j['id'])
    client=client_for(app,people['employer'])
    response=client.post('/api/employer/applications/'+str(a['id'])+'/status',json={'status':'Interviewing'})
    assert response.status_code==200
    assert response.json['application']['score']==66
    assert response.json['application']['rank']==0
    assert response.json['snapshot']['state']['applications'][0]['score']==66
