import os

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.tests.test_api import machine_conditions, receive_type


@pytest.mark.parametrize('rtt', [None, 10, 2500])
def test_common_epoch_and_preroll_clock_estimate(rtt):
    with TestClient(create_app(os.environ['TEST_DATABASE_URL'], countdown_seconds=0.05), client=('127.0.0.1',50000)) as client:
        host=client.post('/api/rooms',json={'name':'sync','record_as_host':True,'required_recorder_count':1}).json()
        base='/api/rooms/'+host['room_code']
        auth={'Authorization':'Bearer '+host['token']}
        assert client.put(base+'/conditions',headers=auth,json=machine_conditions()).status_code==200
        with client.websocket_connect(base+'/ws') as ws:
            ws.send_json({'type':'auth','token':host['token']});receive_type(ws,'state')
            if rtt is not None:
                ws.send_json({'type':'ping','client_ms':1000});pong=receive_type(ws,'pong')
                ws.send_json({'type':'clock','client_sent_ms':1000,'server_received_ms':pong['server_ms'],'client_received_ms':1000+rtt,'performance_ms':100})
                receive_type(ws,'state')
            ws.send_json({'type':'mic','mic':True});receive_type(ws,'state')
            assert client.post(base+'/start',headers=auth).status_code==200
            receive_type(ws,'prepare')
            ws.send_json({'type':'prepared','mime_type':'audio/webm;codecs=opus','sample_rate':48000,'channel_count':1})
            receive_type(ws,'start')
            state=client.get(base,headers=auth).json()
            assert state['started_at']==state['starts_at']
            # Capture began before the common epoch, rather than at ACK arrival.
            ws.send_json({'type':'started','client_ms':995,'performance_ms':85})
            for _ in range(20):
                state=receive_type(ws,'state')['state']
                if state['recordings'][0]['actual_started_at'] is not None:
                    break
            track=state['recordings'][0]
            assert track['actual_started_at']==995
            if rtt==10:
                assert track['capture_server_ms']==pytest.approx(pong['server_ms']-10,abs=0.001)
                assert track['clock_uncertainty_ms']==5
            else:
                assert track['capture_server_ms'] is None
                assert track['clock_uncertainty_ms'] is None
            assert client.post(base+'/stop',headers=auth).status_code==200
