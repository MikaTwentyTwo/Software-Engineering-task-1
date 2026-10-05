"""End-to-end acceptance test against real Compose services; standard library only."""
import concurrent.futures
import json
import os
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

BASE=os.environ.get('BASE_URL','http://localhost:8080')
if Path('.env').exists():
    for line in Path('.env').read_text().splitlines():
        if line and not line.startswith('#') and '=' in line:
            k,v=line.split('=',1); os.environ.setdefault(k,v)


def call(path, method='GET', data=None, token=None, key=None):
    headers={'Content-Type':'application/json'}
    if token: headers['Authorization']='Bearer '+token
    if key: headers['Idempotency-Key']=key
    req=Request(BASE+path, data=json.dumps(data).encode() if data is not None else None, headers=headers, method=method)
    try:
        with urlopen(req,timeout=5) as response:
            return response.status,json.load(response)
    except HTTPError as exc:
        return exc.code,json.loads(exc.read())


def wait(check, description, timeout=120):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        try:
            value=check()
            if value: return value
        except (URLError,TimeoutError,ConnectionError): pass
        time.sleep(1)
    raise AssertionError('Timeout: '+description)


def expect(status, result):
    assert result[0]==status, result
    return result[1]


def main():
    for svc in ['users','rooms','equipment','bookings','notifications','audit']:
        wait(lambda svc=svc: call('/api/'+svc+'/ready')[0]==200,svc+' ready')
    admin=expect(200,call('/api/users/login','POST',{'username':'admin','password':os.environ['ADMIN_PASSWORD']}))['access_token']
    student=expect(200,call('/api/users/login','POST',{'username':'student','password':os.environ['STUDENT_PASSWORD']}))['access_token']
    expect(401,call('/api/bookings/bookings'))
    expect(403,call('/api/rooms/resources','POST',{'name':'Forbidden','capacity':10},student))
    room=expect(201,call('/api/rooms/resources','POST',{'name':'Demo '+str(uuid.uuid4())[:8],'capacity':20},admin))
    equipment=expect(201,call('/api/equipment/resources','POST',{'name':'Demo Projector'},admin))
    wait(lambda: {room['id'],equipment['id']} <= {r['id'] for r in expect(200,call('/api/bookings/resources',token=student))},'resource projections')
    start=datetime.now(timezone.utc)+timedelta(days=1)
    data={'resource_id':room['id'],'start':start.isoformat(),'end':(start+timedelta(hours=1)).isoformat()}
    key=str(uuid.uuid4())
    def create_when_projected():
        result=call('/api/bookings/bookings','POST',data,student,key)
        if result[0]==409 and 'projection' in result[1].get('detail','').lower():
            return None
        return expect(201,result)
    booking=wait(create_when_projected,'user projection and initial booking')
    repeated=expect(201,call('/api/bookings/bookings','POST',data,student,key))
    assert booking['id']==repeated['id']
    expect(409,call('/api/bookings/bookings','POST',{**data,'end':(start+timedelta(hours=2)).isoformat()},student,key))
    expect(409,call('/api/bookings/bookings','POST',data,student,str(uuid.uuid4())))
    wait(lambda: any(n['event']['aggregate_id']==booking['id'] for n in expect(200,call('/api/notifications/notifications',token=student))),'notification')
    wait(lambda: any(e['aggregate_id']==booking['id'] for e in expect(200,call('/api/audit/events',token=admin))),'audit')
    expect(403,call('/api/audit/events',token=student))
    expect(200,call('/api/bookings/bookings/'+booking['id'],'DELETE',token=student))
    expect(200,call('/api/bookings/bookings/'+booking['id'],'DELETE',token=student))
    time.sleep(1) # Let the IP limiter refill before the race.
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _: call('/api/bookings/bookings','POST',data,student,str(uuid.uuid4())),range(2)))
    assert sorted(r[0] for r in results)==[201,409],results
    winner=next(r[1] for r in results if r[0]==201)
    expect(200,call('/api/bookings/bookings/'+winner['id'],'DELETE',token=student))
    # Admin owns this equipment reservation; student must not cancel it.
    other=expect(201,call('/api/bookings/bookings','POST',{**data,'resource_id':equipment['id']},admin,str(uuid.uuid4())))
    expect(403,call('/api/bookings/bookings/'+other['id'],'DELETE',token=student))
    expect(200,call('/api/bookings/bookings/'+other['id'],'DELETE',token=admin))
    print('PASS: auth, roles, projections, idempotency, conflict, notification, audit, cancellation, concurrency, ownership')

if __name__=='__main__': main()
