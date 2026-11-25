"""Supplement: real JSON authentication boundaries and generated valid slots.

Uses the actual request/service entry points, isolated fixtures and fixed seeds.
No resume-authorization policy is changed by these tests.
"""
from datetime import datetime, timedelta, timezone
import calendar
import random

import pytest

SEED=48012027


def auth_state():
    from recruiting.db import get_db
    db=get_db()
    return tuple(tuple(row) for row in db.execute('SELECT * FROM users ORDER BY id')), tuple(
        tuple(row) for row in db.execute('SELECT * FROM auth_sessions ORDER BY token_hash'))


def test_register_and_login_reject_roles_without_writes(app):
    client=app.test_client()
    data={'email':'new@example.test','password':'DemoPass123!','name':'New Person'}
    for role in (None,'Admin','candidate','Employer ','',True,0,[],{}):
        before=auth_state()
        for endpoint in ('register','login'):
            response=client.post('/api/auth/'+endpoint,json={**data,'role':role})
            assert response.status_code==400,(role,response.json)
            assert response.json['ok'] is False and auth_state()==before
    assert client.get('/api/auth/me').status_code==401


def test_credentials_type_length_and_email_boundaries(app):
    from recruiting.db import get_db
    client=app.test_client()
    original={'email':'a@example.test','password':'DemoPass123!','role':'Candidate','name':'Person'}
    assert client.post('/api/auth/register',json=original).status_code==201
    client.post('/api/auth/logout')
    for field in ('email','password'):
        for value in (None,True,3,[],{},'x'*257):
            before=auth_state()
            response=client.post('/api/auth/login',json={**original,field:value})
            assert response.status_code==401 and auth_state()==before,(field,value,response.json)
    for field in ('email','password','name'):
        for value in (None,True,3,[],{}):
            before=auth_state()
            response=client.post('/api/auth/register',json={**original,field:value})
            assert response.status_code==400 and auth_state()==before,(field,value,response.json)
    for password in ('p'*7,'p'*257):
        before=auth_state()
        assert client.post('/api/auth/register',json={
            **original,'email':'length@example.test','password':password}).status_code==400
        assert auth_state()==before
    for index,password in enumerate(('p'*8,'p'*256)):
        assert client.post('/api/auth/register',json={
            **original,'email':'valid'+str(index)+'@example.test','password':password}).status_code==201
    suffix='@example.test'
    longest='a'*(254-len(suffix))+suffix
    assert client.post('/api/auth/register',json={**original,'email':longest}).status_code==201
    before=auth_state()
    assert client.post('/api/auth/register',json={**original,'email':'a'+longest}).status_code==400
    assert auth_state()==before
    assert client.post('/api/auth/register',json={**original,'email':' A@EXAMPLE.TEST '}).status_code==409
    assert get_db().execute('SELECT count(*) FROM users').fetchone()[0]==4


def test_rotated_and_expired_sessions_cannot_be_reused(app):
    client=app.test_client()
    data={'email':'session@example.test','password':'DemoPass123!','role':'Candidate','name':'Session Person'}
    assert client.post('/api/auth/register',json=data).status_code==201
    first=client.get_cookie('session').value
    assert client.post('/api/auth/login',json=data).status_code==200
    replay=app.test_client()
    replay.set_cookie('session',first)
    assert replay.get('/api/auth/me').status_code==401
    assert client.get('/api/auth/me').status_code==200
    app.config['NOW']=lambda:datetime(2030,1,1,21,tzinfo=timezone.utc)
    assert client.get('/api/auth/me').status_code==401
    assert client.post('/api/auth/login',json=data).status_code==200
    assert client.get('/api/auth/me').status_code==200


@pytest.mark.parametrize('edge',['\ufeff','\u0085','\u001c','\u00a0','\u2003','\u3000'])
def test_unicode_edge_whitespace_persists_and_matches_both_services(app,people,edge):
    from recruiting import accounts,jobs
    from recruiting.db import get_db
    c,e=people['candidate'],people['employer']
    client=app.test_client()
    assert client.post('/api/auth/login',json={
        'email':c['email'],'password':'DemoPass123!','role':'Candidate'}).status_code==200
    response=client.post('/api/candidate/profile',json={'skills':[edge+'Python'+edge,edge]})
    assert response.status_code==200
    assert response.json['profile']['skills']==['python']
    j=jobs.create_job(e,'Unicode match','Description',['Python','SQL','Rust'])
    jobs.apply(c,j['id'])
    assert jobs.recommendations(c)[0]['score']==33
    assert jobs.applicants(e,j['id'])[0]['score']==33
    assert get_db().execute('SELECT skill FROM candidate_skills WHERE candidate_id=?',(c['id'],)).fetchone()[0]=='python'


def test_generated_future_slots_and_offsets_have_exact_utc(people):
    from recruiting import jobs,scheduling
    from recruiting.db import get_db
    from recruiting.errors import DomainError
    rng=random.Random(SEED)
    e=people['employer']
    j=jobs.create_job(e,'Generated slots','Description',[])
    offsets=(-720,-480,-210,0,330,480,840)
    for index in range(120):
        year=rng.randrange(2031,2036); month=rng.randrange(1,13)
        day=rng.randrange(1,calendar.monthrange(year,month)[1]+1)
        utc=datetime(year,month,day,rng.randrange(24),rng.randrange(60),rng.randrange(60),tzinfo=timezone.utc)
        zone=timezone(timedelta(minutes=rng.choice(offsets)))
        start=utc.astimezone(zone).isoformat()
        end=(utc+timedelta(minutes=30)).astimezone(zone).isoformat()
        slot=scheduling.create_slot(e,j['id'],start,end)
        witness=(SEED,index,start,end)
        assert slot['starts_at']==int(utc.timestamp()),witness
        assert slot['ends_at']==int(utc.timestamp())+1800,witness
        before=get_db().execute('SELECT count(*) FROM slots').fetchone()[0]
        with pytest.raises(DomainError) as caught:
            scheduling.create_slot(e,j['id'],start,(utc+timedelta(seconds=1799)).astimezone(zone).isoformat())
        assert caught.value.status==400,witness
        assert get_db().execute('SELECT count(*) FROM slots').fetchone()[0]==before,witness


def test_seeded_application_booking_operation_model(people):
    from recruiting import jobs,scheduling
    from recruiting.db import get_db
    from recruiting.errors import DomainError
    rng=random.Random(SEED)
    e,e2=people['employer'],people['employer2']
    candidates=[people['candidate'],people['candidate2']]
    j=jobs.create_job(e,'Model role','Description',[])
    foreign=jobs.create_job(e2,'Other employer','Description',[])
    applications=[jobs.apply(c,j['id']) for c in candidates]
    model={a['id']:{'status':'Pending','slot':None} for a in applications}
    slots={}
    for index in range(7):
        owner=e2 if index==6 else e
        slot=scheduling.create_slot(owner,foreign['id'] if index==6 else j['id'],
          '2031-01-02T'+str(10+index).zfill(2)+':00:00Z',
          '2031-01-02T'+str(10+index).zfill(2)+':30:00Z')
        slots[slot['id']]={'foreign':index==6,'application':None,'active':True}
    # Establish a reserved application first, then explore mutations of its status.
    first=applications[0]['id']; first_slot=next(iter(slots))
    jobs.set_status(e,first,'Interviewing')
    scheduling.book(candidates[0],first,first_slot)
    model[first].update(status='Interviewing',slot=first_slot)
    slots[first_slot]['application']=first
    trace=[]
    for index in range(120):
        app_index=rng.randrange(2); application=applications[app_index]; aid=application['id']
        operation=rng.choice(('status','book','delete','view'))
        state=model[aid]
        def snapshot():
            return {t:[tuple(r) for r in get_db().execute('SELECT * FROM '+t+' ORDER BY id')]
                    for t in ('jobs','applications','slots','bookings')}
        before=snapshot()
        expected=None
        if operation=='status':
            status=rng.choice(('Pending','Interviewing','Rejected','Accepted','Invalid'))
            actor=e2 if rng.randrange(8)==0 else e
            expected=403 if actor==e2 else 400 if status=='Invalid' else None
            call=lambda:jobs.set_status(actor,aid,status)
            args=(aid,status,actor['id'])
        elif operation=='book':
            sid=rng.choice(list(slots)); slot=slots[sid]
            actor=candidates[1-app_index] if rng.randrange(8)==0 else candidates[app_index]
            # Match the integrated security contract: reject an ineligible
            # application before looking up a slot belonging to anyone else.
            expected=(403 if actor['id']!=application['candidate_id'] else
                      409 if state['slot'] is not None or state['status']!='Interviewing' else
                      404 if not slot['active'] else 403 if slot['foreign'] else
                      409 if slot['application'] is not None else None)
            call=lambda:scheduling.book(actor,aid,sid)
            args=(aid,sid,actor['id'])
        elif operation=='delete':
            sid=rng.choice(list(slots)); slot=slots[sid]
            expected=(404 if not slot['active'] else 403 if slot['foreign'] else
                      409 if slot['application'] is not None else None)
            call=lambda:scheduling.delete_slot(e,sid)
            args=(sid,)
        else:
            call=lambda:jobs.application(candidates[app_index],aid)
            args=(aid,)
        trace.append((operation,args,expected))
        witness=(SEED,index,trace)
        if expected is not None:
            with pytest.raises(DomainError) as caught:
                call()
            assert caught.value.status==expected,witness
            assert snapshot()==before,witness
        else:
            call()
            if operation=='status': state['status']=status
            elif operation=='book':
                state['slot']=sid; slots[sid]['application']=aid
            elif operation=='delete': slots[sid]['active']=False
        for check_index,application in enumerate(applications):
            actual=jobs.application(candidates[check_index],application['id'])
            expected_state=model[application['id']]
            assert actual['status']==expected_state['status'],witness
            assert (actual['booking']['slot_id'] if actual['booking'] else None)==expected_state['slot'],witness
        booked=get_db().execute('SELECT count(*) FROM bookings').fetchone()[0]
        assert booked==sum(state['slot'] is not None for state in model.values()),witness
