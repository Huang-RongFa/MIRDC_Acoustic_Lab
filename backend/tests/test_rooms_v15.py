import os
import re

from fastapi.testclient import TestClient
from backend.app import create_app


def test_secure_six_character_codes_and_room_identity():
    with TestClient(create_app(os.environ['TEST_DATABASE_URL'])) as client:
        rooms = [client.post('/api/rooms', json={'name': 'A'}).json() for _ in range(20)]
        assert all(re.fullmatch(r'[ABCDEFGHJKLMNPQRSTUVWXYZ23456789]{6}', r['room_code']) for r in rooms)
        assert len({r['room_code'] for r in rooms}) == 20
        assert all(r['room_id'] and r['token'] for r in rooms)


def test_code_collision_retries_without_overwriting_room(monkeypatch):
    import backend.app as module
    with TestClient(create_app(os.environ['TEST_DATABASE_URL'])) as c:
        first=c.post('/api/rooms',json={'name':'A'}).json()
        # Force one collision at the randomness boundary, then resume secure generation.
        choice=module.secrets.choice
        letters=iter(first['room_code'])
        monkeypatch.setattr(module.secrets,'choice',lambda alphabet:next(letters,None) or choice(alphabet))
        second=c.post('/api/rooms',json={'name':'second'}).json()
        assert second['room_code']!=first['room_code']
        original=c.get('/api/rooms/'+first['room_code'],headers={'Authorization':'Bearer '+first['token']}).json()
        assert original['id']==first['session_id']


def test_auto_slots_rejoin_and_close():
    with TestClient(create_app(os.environ['TEST_DATABASE_URL'])) as c:
        host = c.post('/api/rooms', json={'name': 'A'}).json()
        base = '/api/rooms/' + host['room_code']
        auth = {'Authorization': 'Bearer ' + host['token']}
        b = c.post(base + '/join', json={'name': 'B'}).json()
        third = c.post(base + '/join', json={'name': 'C'})
        assert third.status_code == 201
        assert third.json()['source_label'] == 'C'
        assert c.post(base + '/join', json={'name': 'fourth'}).status_code == 409
        restored = c.post(base + '/join', headers={'Authorization': 'Bearer ' + b['token']}, json={'name': 'B'})
        assert restored.status_code == 200
        assert restored.json()['participant_id'] == b['participant_id']
        assert c.post(base + '/close', headers={'Authorization': 'Bearer ' + b['token']}).status_code == 403
        assert c.post(base + '/close', headers=auth).status_code == 200
        assert c.post(base + '/join', json={'name': 'late'}).status_code == 410
        assert c.post(base + '/start', headers=auth).status_code == 410


def test_expired_room_cannot_join():
    import psycopg
    with TestClient(create_app(os.environ['TEST_DATABASE_URL'])) as c:
        host = c.post('/api/rooms', json={'name': 'A'}).json()
        with psycopg.connect(os.environ['TEST_DATABASE_URL']) as db:
            db.execute("UPDATE mobile_capture.recording_rooms SET expires_at=now()-interval '1 second' WHERE id=%s", (host['room_id'],))
        assert c.post('/api/rooms/' + host['room_code'] + '/join', json={'name': 'B'}).status_code == 410


def test_disconnect_reports_uncertainty_and_reconnect_keeps_slot():
    from backend.tests.test_api import receive_type
    with TestClient(create_app(os.environ['TEST_DATABASE_URL'])) as c:
        host = c.post('/api/rooms', json={'name': 'A'}).json()
        path = '/api/rooms/' + host['room_code']
        headers = {'Authorization':'Bearer '+host['token']}
        with c.websocket_connect(path + '/ws') as ws:
            ws.send_json({'type':'auth','token':host['token']})
            receive_type(ws, 'state')
        state = c.get(path, headers=headers).json()
        assert state['participants'][0]['error']
        assert state['ready_count'] == 0
        with c.websocket_connect(path + '/ws') as ws:
            ws.send_json({'type':'auth','token':host['token']})
            restored = receive_type(ws, 'state')['state']
            assert len(restored['participants']) == 1
            assert restored['participants'][0]['id'] == host['participant_id']
            assert restored['participants'][0]['connected']


def test_missing_start_ack_and_finish_are_reported_without_automatic_stop():
    import time
    from contextlib import ExitStack
    from backend.tests.test_api import CONDITIONS, receive_type
    with TestClient(create_app(os.environ['TEST_DATABASE_URL'], countdown_seconds=0.01,
                              acknowledgement_seconds=0.05, finalization_seconds=0.05)) as c, ExitStack() as stack:
        host = c.post('/api/rooms', json={'name':'A'}).json()
        path = '/api/rooms/' + host['room_code']
        auth = {'Authorization':'Bearer '+host['token']}
        people = [host]+[c.post(path+'/join',json={'name':label}).json() for label in 'BC']
        c.put(path+'/conditions',headers=auth,json=CONDITIONS)
        sockets=[]
        for person in people:
            ws=stack.enter_context(c.websocket_connect(path+'/ws'))
            ws.send_json({'type':'auth','token':person['token']})
            receive_type(ws,'state')
            ws.send_json({'type':'ready','mic':True})
            receive_type(ws,'state')
            sockets.append(ws)
        assert c.post(path+'/start',headers=auth).status_code==200
        for ws in sockets:
            receive_type(ws,'prepare')
            ws.send_json({'type':'prepared','mime_type':'audio/webm'})
        for ws in sockets:
            receive_type(ws,'start')
        time.sleep(0.15)
        state=c.get(path,headers=auth).json()
        assert state['status']=='recording'  # ACK timeout reports failure, never stops capture.
        assert all(r['error'] and r['status']=='failed' for r in state['recordings'])
        assert c.post(path+'/stop',headers=auth).status_code==200
        time.sleep(0.15)
        state=c.get(path,headers=auth).json()
        assert state['status']=='interrupted'
        assert all(r['error'] for r in state['recordings'])
