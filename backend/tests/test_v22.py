import hashlib
import os
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient

from backend.app import create_app


@pytest.fixture
def client():
    with TestClient(create_app(os.environ['TEST_DATABASE_URL'],countdown_seconds=0),client=('127.0.0.1',50000)) as http:
        yield http


def auth(member):
    return {'Authorization':'Bearer '+member['token']}


@pytest.mark.parametrize('count',range(1,6))
def test_assignments(client,count):
    host=client.post('/api/rooms',json={'name':'主控','required_recorder_count':count}).json()
    base='/api/rooms/'+host['room_code']
    members=[client.post(base+'/join',json={'name':str(i)}).json() for i in range(count)]
    assert [p['source_label'] for p in members]==list('ABCDE'[:count])
    assert host['source_label'] is None
    assert client.post(base+'/join',json={'name':'超額'}).status_code==409
    assert client.post(base+'/start',headers=auth(host)).status_code==422
    assert client.post(base+'/close',headers=auth(members[0])).status_code==403
    if count>1:
        assert client.patch(base+'/participants/'+members[0]['participant_id'],headers=auth(host),json={'swap_with':members[1]['participant_id']}).status_code==405
    assert client.post(base+'/leave',headers=auth(members[0])).is_success
    assert client.get(base,headers=auth(members[0])).status_code==403
    assert client.post(base+'/join',json={'name':'替補'}).is_success
    assert client.post(base+'/close',headers=auth(host)).is_success
    assert client.post(base+'/join',json={'name':'重連'}).status_code==410


def until(ws,kind):
    while True:
        event=ws.receive_json()
        if event['type']==kind:
            return event


def test_repeated_capture(client):
    with psycopg.connect(os.environ['TEST_DATABASE_URL']) as db:
        machine=db.execute('INSERT INTO public.machines(machine_code,machine_name,machine_type) VALUES(%s,%s,%s) RETURNING machine_id',(str(uuid4()),'測試設備','幫浦')).fetchone()[0]
    host=client.post('/api/rooms',json={'name':'主控','required_recorder_count':1}).json()
    base='/api/rooms/'+host['room_code']
    phone=client.post(base+'/join',json={'name':'手機'}).json()
    assert client.put(base+'/conditions',headers=auth(host),json={'machine_id':str(uuid4())}).status_code==422
    assert client.put(base+'/conditions',headers=auth(host),json={'machine_id':str(machine)}).is_success
    takes=set()
    with client.websocket_connect('/ws/rooms/'+host['room_code']) as ws:
        ws.send_json({'type':'auth','token':phone['token']})
        until(ws,'state')
        for i in range(3):
            ws.send_json({'type':'mic','mic':True})
            ws.send_json({'type':'ready','mic':True})
            while until(ws,'state')['state']['ready_count']!=1:
                pass
            assert client.post(base+'/start',headers=auth(host)).is_success
            take=until(ws,'prepare')['session_id']
            assert take not in takes
            takes.add(take)
            ws.send_json({'type':'prepared','mime_type':'audio/webm','sample_rate':48000,'channel_count':1})
            until(ws,'start')
            ws.send_json({'type':'started','client_ms':100,'performance_ms':1})
            while not until(ws,'state')['state']['recordings'][0]['actual_started_at']:
                pass
            track=base+'/recordings/'+phone['participant_id']
            data=('測試分段'+str(i)).encode()
            query={'take_id':take}
            headers={**auth(phone),'Content-Type':'audio/webm','X-Checksum':hashlib.sha256(data).hexdigest(),'X-Created-At':'101'}
            assert client.put(track+'/chunks/0',params=query,headers=headers,content=data).is_success
            assert client.post(base+'/stop',headers=auth(host)).is_success
            assert client.post(track+'/finish',params=query,headers=auth(phone),json={'client_ms':200,'chunk_count':1}).is_success
            assert client.get(track+'/audio',params=query,headers=auth(host)).content==data
            if i<2:
                assert client.post(base+'/next',headers=auth(host)).is_success
    assert len(takes)==3


def test_five_recorders_close_during_capture(client):
    from contextlib import ExitStack
    with psycopg.connect(os.environ['TEST_DATABASE_URL']) as db:
        machine=db.execute('INSERT INTO public.machines(machine_code,machine_name,machine_type) VALUES(%s,%s,%s) RETURNING machine_id',(str(uuid4()),'測試加工機','CNC')).fetchone()[0]
    host=client.post('/api/rooms',json={'name':'主控','required_recorder_count':5}).json()
    base='/api/rooms/'+host['room_code']
    assert client.put(base+'/conditions',headers=auth(host),json={'machine_id':str(machine),'spindle_rpm':400}).is_success
    with ExitStack() as stack:
        members=[]
        for index in range(5):
            phone=client.post(base+'/join',json={'name':str(index)}).json()
            ws=stack.enter_context(client.websocket_connect('/ws/rooms/'+host['room_code']))
            ws.send_json({'type':'auth','token':phone['token']})
            until(ws,'state')
            ws.send_json({'type':'mic','mic':True})
            ws.send_json({'type':'ready','mic':True})
            while until(ws,'state')['state']['ready_count']!=index+1:
                pass
            members.append((phone,ws))
        assert client.post(base+'/start',headers=auth(host)).is_success
        assert client.post(base+'/start',headers=auth(host)).is_success
        for phone,ws in members:
            take=until(ws,'prepare')['session_id']
            ws.send_json({'type':'prepared','mime_type':'audio/webm','sample_rate':44100,'channel_count':1})
        for phone,ws in members:
            until(ws,'start')
            ws.send_json({'type':'started','client_ms':100,'performance_ms':1})
            while not next(r for r in until(ws,'state')['state']['recordings'] if r['participant_id']==phone['participant_id'])['actual_started_at']:
                pass
        assert client.post(base+'/close',headers=auth(host)).is_success
        assert client.post(base+'/close',headers=auth(host)).is_success
        with psycopg.connect(os.environ['TEST_DATABASE_URL']) as db:
            db.execute("UPDATE public.machines SET machine_name='已改名' WHERE machine_id=%s",(machine,))
        assert client.get(base,headers=auth(host)).json()['conditions']['machine_name']=='測試加工機'
        for phone,ws in members:
            until(ws,'stop')
            data=phone['participant_id'].encode()
            track=base+'/recordings/'+phone['participant_id']
            query={'take_id':take}
            h={**auth(phone),'Content-Type':'audio/webm','X-Created-At':'101','X-Checksum':hashlib.sha256(data).hexdigest()}
            assert client.put(track+'/chunks/0',params=query,headers=h,content=data).is_success
            assert client.post(track+'/finish',params=query,headers=auth(phone),json={'client_ms':200,'chunk_count':1}).is_success
        for _,ws in members:
            until(ws,'room_closed')
    assert client.get(base,headers=auth(host)).status_code==403
    with psycopg.connect(os.environ['TEST_DATABASE_URL']) as db:
        assert db.execute('SELECT count(DISTINCT checksum) FROM mobile_capture.audio_assets WHERE session_id=%s',(take,)).fetchone()[0]==5


def test_external_network_denied():
    app=create_app(os.environ['TEST_DATABASE_URL'])
    with TestClient(app,client=('203.0.113.1',50000)) as http:
        assert http.post('/api/rooms',json={'name':'主控'}).status_code==403


def test_manual_machine_entry(client):
    host=client.post('/api/rooms',json={'name':'主控'}).json()
    base='/api/rooms/'+host['room_code']
    code='幫浦-'+str(uuid4())
    headers=auth(host)
    assert client.put(base+'/conditions',headers=headers,json={'machine_code':'   '}).status_code==422
    for value in [' '+code+' ',code]:
        assert client.put(base+'/conditions',headers=headers,json={'machine_code':value}).is_success
        saved=client.get(base,headers=headers).json()['conditions']
        assert saved['machine_code']==code and saved['machine_id']
    with psycopg.connect(os.environ['TEST_DATABASE_URL']) as db:
        assert db.execute('SELECT count(*) FROM public.machines WHERE machine_code=%s',(code,)).fetchone()[0]==1


def test_microphone_automatically_ready_and_start(client):
    host=client.post('/api/rooms',json={'name':'主控','required_recorder_count':1}).json()
    base='/api/rooms/'+host['room_code']
    phone=client.post(base+'/join',json={'name':'手機'}).json()
    assert client.put(base+'/conditions',headers=auth(host),json={'machine_code':str(uuid4())}).is_success
    with client.websocket_connect('/ws/rooms/'+host['room_code']) as ws:
        ws.send_json({'type':'auth','token':phone['token']})
        assert until(ws,'state')['state']['ready_count']==0
        assert client.post(base+'/start',headers=auth(host)).status_code==409
        for enabled in (True,False,True):
            ws.send_json({'type':'mic','mic':enabled})
            state=until(ws,'state')['state']
            assert state['ready_count']==int(enabled)
            member=next(p for p in state['participants'] if p['id']==phone['participant_id'])
            assert member['ready'] is enabled
            assert member['is_ready'] is enabled
        assert client.post(base+'/start',headers=auth(host)).is_success
        until(ws,'prepare')
        ws.send_json({'type':'prepared','mime_type':'audio/webm','sample_rate':48000,'channel_count':1})
        until(ws,'start')
        assert client.get(base,headers=auth(host)).json()['status']=='recording'
    assert client.get(base,headers=auth(host)).json()['ready_count']==0
