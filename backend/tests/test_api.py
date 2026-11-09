import os

from fastapi.testclient import TestClient

from backend.app import create_app

CONDITIONS = dict(machine_code='CNC-01', machine_name='測試機台', machine_model='VMC', material='AL6061', material_spec='T6', workpiece_code='W1', tool_type='平銑刀', tool_material='硬質合金', tool_diameter_mm=10, tool_flutes=4, tool_overhang_mm=35, tool_setup='ER32', spindle_rpm=6000, feed_mm_min=600, axial_depth_mm=0.5, radial_width_mm=2, process='銑削', coolant='乾式', toolpath='平行', nc_program='O001')


def receive_type(ws, kind):
    for _ in range(30):
        message = ws.receive_json()
        if message['type'] == kind:
            return message
    raise AssertionError('Missing event: ' + kind)


def test_three_participants_prepare_start_stop_and_real_preview():
    from contextlib import ExitStack
    with TestClient(create_app(os.environ['TEST_DATABASE_URL'], countdown_seconds=0.05)) as c, ExitStack() as stack:
        host = c.post('/api/rooms', json={'name':'A'}).json()
        code = host['room_code']
        people = [host] + [c.post(f'/api/rooms/{code}/join', json={'name':s,'source_label':s}).json() for s in ['B','C']]
        headers = {'Authorization':'Bearer '+host['token']}
        assert c.put(f'/api/rooms/{code}/conditions', headers=headers, json=CONDITIONS).status_code == 200
        sockets = []
        for person in people:
            ws = stack.enter_context(c.websocket_connect(f'/api/rooms/{code}/ws'))
            ws.send_json({'type':'auth','token':person['token']})
            receive_type(ws, 'state')
            ws.send_json({'type':'ready','mic':True})
            receive_type(ws, 'state')
            sockets.append(ws)
        assert c.post(f'/api/rooms/{code}/start',headers=headers).status_code == 200
        for ws in sockets:
            receive_type(ws,'prepare')
            ws.send_json({'type':'prepared','mime_type':'audio/webm;codecs=opus','sample_rate':48000,'channel_count':1})
        for index, ws in enumerate(sockets):
            receive_type(ws,'start')
            if index < 2:
                ws.send_json({'type':'started','client_ms':1000,'performance_ms':100})
                receive_type(ws,'state')
        sockets[1].send_json({'type':'preview','samples':[0,0.25,-0.25]})
        preview = receive_type(sockets[0],'preview')
        assert preview['source_label'] == 'B'
        assert preview['samples'] == [0,0.25,-0.25]
        state = c.get(f'/api/rooms/{code}',headers=headers).json()
        assert state['status'] == 'recording'
        assert state['started_at'] is not None
        assert c.put(f'/api/rooms/{code}/conditions',headers=headers,json=CONDITIONS).status_code == 409
        assert c.post(f'/api/rooms/{code}/stop',headers=headers).status_code == 200
        for ws in sockets:
            receive_type(ws,'stop')
        assert c.get(f'/api/rooms/{code}',headers=headers).json()['status'] == 'finalizing'
        sockets[2].send_json({'type':'started','client_ms':1000,'performance_ms':100})
        receive_type(sockets[2],'state')
        import hashlib
        for person in people:
            auth = {'Authorization':'Bearer '+person['token']}
            base = f"/api/rooms/{code}/recordings/{person['participant_id']}"
            data = b'webm-test-bytes-' + person['source_label'].encode()
            chunk_headers = {**auth,'Content-Type':'audio/webm;codecs=opus','X-Checksum':hashlib.sha256(data).hexdigest(),'X-Created-At':'1001'}
            assert c.put(base+'/chunks/0',headers=chunk_headers,content=data).status_code == 200
            assert c.put(base+'/chunks/0',headers=chunk_headers,content=data).status_code == 200
            assert c.put(base+'/chunks/0',headers={**chunk_headers,'X-Checksum':hashlib.sha256(b'conflict').hexdigest()},content=b'conflict').status_code == 409
            assert c.post(base+'/finish',headers=auth,json={'chunk_count':2,'client_ms':2000}).status_code == 409
            assert c.put(base+'/chunks/1',headers=chunk_headers,content=data).status_code == 200
            assert c.post(base+'/finish',headers=auth,json={'chunk_count':2,'client_ms':2000,'duration_ms':1000}).status_code == 200
            assert c.get(base+'/audio',headers=headers).content == data+data
        result = c.get(f'/api/rooms/{code}',headers=headers).json()
        assert result['status'] == 'completed'
        assert len({r['participant_recording_id'] for r in result['recordings']}) == 3
        for r in result['recordings']:
            assert r['sample_rate'] == 48000
            assert r['duration_ms'] == 1000
            assert r['byte_size'] > 0
            assert r['received_chunks'] == r['expected_chunks'] == 2
            assert r['missing_chunks'] == 0
            assert r['server_started_at'] is not None
            assert r['server_stopped_at'] is not None
        assert c.post(base+'/finish',headers=auth,json={'chunk_count':2,'client_ms':2000,'interrupted':True}).status_code == 409
        assert c.get(f'/api/rooms/{code}',headers=headers).json()['status'] == 'completed'


def test_conditions_accept_submillimeter_tools_and_reject_out_of_range():
    with TestClient(create_app(os.environ['TEST_DATABASE_URL'])) as c:
        host=c.post('/api/rooms',json={'name':'A'}).json()
        path=f"/api/rooms/{host['room_code']}/conditions"
        auth={'Authorization':'Bearer '+host['token']}
        assert c.put(path,headers=auth,json={**CONDITIONS,'tool_diameter_mm':0.5}).status_code==200
        assert c.put(path,headers=auth,json={**CONDITIONS,'tool_diameter_mm':1001}).status_code==422
        assert c.put(path,headers=auth,json={**CONDITIONS,'spindle_rpm':-1}).status_code==422


def test_room_assigns_host_a_and_limits_sources():
    with TestClient(create_app(os.environ['TEST_DATABASE_URL'], countdown_seconds=0.05)) as client:
        response = client.post('/api/rooms', json={'name': '主控者'})
        assert response.status_code == 201
        host = response.json()
        headers = {'Authorization': 'Bearer ' + host['token']}
        room = host['room_code']
        state = client.get('/api/rooms/' + room, headers=headers).json()
        assert state['participants'][0]['source_label'] == 'A'
        assert state['ready_count'] == 0
        assert client.post(f'/api/rooms/{room}/start', headers=headers).status_code == 409
        assert client.get('/api/rooms/' + room).status_code == 401
        b = client.post(f'/api/rooms/{room}/join', json={'name': 'B', 'source_label': 'B'})
        assert b.status_code == 201
        assert client.post(f'/api/rooms/{room}/join', json={'name': 'other', 'source_label': 'B'}).status_code == 409
        assert client.post(f'/api/rooms/{room}/stop', headers={'Authorization': 'Bearer ' + b.json()['token']}).status_code == 403
