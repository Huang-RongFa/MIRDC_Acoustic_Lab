import os

import psycopg
import pytest
from fastapi.testclient import TestClient

from backend.app import create_app


def receive(ws, kind):
    while True:
        message = ws.receive_json()
        if message['type'] == kind:
            return message


@pytest.mark.parametrize('action', ['kick', 'leave'])
def test_waiting_departure_after_clock_sync(action):
    with TestClient(create_app(os.environ['TEST_DATABASE_URL']), client=('127.0.0.1', 50000)) as client:
        host = client.post('/api/rooms', json={'name': 'host'}).json()
        base = '/api/rooms/' + host['room_code']
        members = [client.post(base + '/join', json={'name': name}).json() for name in ['target', 'remaining']]
        for member in members:
            with client.websocket_connect(base + '/ws') as ws:
                ws.send_json({'type': 'auth', 'token': member['token']})
                receive(ws, 'state')
                ws.send_json({'type': 'ping', 'client_ms': 1000})
                pong = receive(ws, 'pong')
                ws.send_json({'type': 'clock', 'client_sent_ms': 1000, 'server_received_ms': pong['server_ms'], 'client_received_ms': 1001, 'performance_ms': 10})
                receive(ws, 'state')
        target, remaining = members
        with psycopg.connect(os.environ['TEST_DATABASE_URL']) as db:
            assert db.execute('SELECT count(*) FROM mobile_capture.device_clock_observations WHERE session_id=%s', (host['session_id'],)).fetchone()[0] == 2
        auth = {'Authorization': 'Bearer ' + host['token']}
        if action == 'kick':
            response = client.delete(base + '/participants/' + target['participant_id'], headers=auth)
        else:
            response = client.post(base + '/leave', headers={'Authorization': 'Bearer ' + target['token']})
        assert response.status_code == 200
        state = client.get(base, headers=auth).json()
        assert target['participant_id'] not in [p['id'] for p in state['participants']]
        assert remaining['participant_id'] in [p['id'] for p in state['participants']]
        assert client.get(base, headers={'Authorization': 'Bearer ' + target['token']}).status_code == 403
        replacement = client.post(base + '/join', json={'name': 'replacement'})
        assert replacement.status_code == 201
        assert replacement.json()['source_label'] == target['source_label']
        with psycopg.connect(os.environ['TEST_DATABASE_URL']) as db:
            clocks = db.execute('SELECT participant_id FROM mobile_capture.device_clock_observations WHERE session_id=%s', (host['session_id'],)).fetchall()
            assert [str(row[0]) for row in clocks] == [remaining['participant_id']]
