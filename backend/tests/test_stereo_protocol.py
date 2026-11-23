import pytest
from backend.capture_protocol import capture_settings, preview_channels


def test_stereo_settings_and_preview_reject_fake_channels():
    message={'requested_sample_rate':44100,'requested_channel_count':2,'input_sample_rate':48000,'actual_sample_rate':44100,'channel_count':2,'support_status':'ready'}
    assert capture_settings(message)['actual_sample_rate']==44100
    with pytest.raises(ValueError):capture_settings({**message,'channel_count':1})
    with pytest.raises(ValueError):capture_settings({**message,'requested_channel_count':True})
    assert preview_channels({'channels':[[.1,.2],[-.1,-.2]]})==[[.1,.2],[-.1,-.2]]
    for channels in [[[1],[1],[1]], [[1],[1,2]], [[float('nan')]], [[2]], [[True]]]:
        assert preview_channels({'channels':channels}) is None


def test_stereo_offline_resampling_keeps_left_and_right_distinct():
    import numpy as np
    from backend.audio_sync import analysis_copy,align_copy
    t=np.arange(44100)/44100
    stereo=np.column_stack([.1*np.sin(2*np.pi*440*t),.2*np.sin(2*np.pi*880*t)]).astype(np.float32)
    converted=analysis_copy(stereo,44100)
    assert converted.shape==(48000,2)
    assert not np.array_equal(converted[:,0],converted[:,1])
    for i,freq in enumerate([440,880]):
        assert np.argmax(abs(np.fft.rfft(converted[:,i])))==freq
    assert align_copy(converted,-48).shape==(48048,2)
    assert align_copy(converted,48).shape==(47952,2)


def test_three_recorders_preserve_121_channels_and_broadcast_stereo():
    import os,hashlib
    from contextlib import ExitStack
    from fastapi.testclient import TestClient
    from backend.app import create_app
    from backend.tests.test_api import receive_type,machine_conditions
    with TestClient(create_app(os.environ['TEST_DATABASE_URL'],countdown_seconds=.05),client=('127.0.0.1',50000)) as client,ExitStack() as stack:
        host=client.post('/api/rooms',json={'name':'controller','required_recorder_count':3}).json()
        base='/api/rooms/'+host['room_code'];auth={'Authorization':'Bearer '+host['token']}
        assert client.put(base+'/conditions',headers=auth,json=machine_conditions()).status_code==200
        people=[client.post(base+'/join',json={'name':f'device{i}'}).json() for i in range(3)]
        sockets=[]
        for person,channels,rate in zip(people,[1,2,1],[48000,44100,48000]):
            ws=stack.enter_context(client.websocket_connect(base+'/ws'));ws.send_json({'type':'auth','token':person['token']});receive_type(ws,'state')
            ws.send_json({'type':'capture_settings','requested_sample_rate':rate,'requested_channel_count':channels,'actual_sample_rate':rate,'input_sample_rate':rate,'channel_count':channels,'support_status':'ready'});receive_type(ws,'state')
            ws.send_json({'type':'mic','mic':True});receive_type(ws,'state');sockets.append(ws)
        assert client.post(base+'/start',headers=auth).status_code==200
        for ws,channels,rate in zip(sockets,[1,2,1],[48000,44100,48000]):
            receive_type(ws,'prepare');ws.send_json({'type':'prepared','mime_type':'audio/webm;codecs=opus','sample_rate':rate,'channel_count':channels})
        for ws in sockets:
            receive_type(ws,'start');ws.send_json({'type':'started','client_ms':1000,'performance_ms':100});receive_type(ws,'state')
        sockets[1].send_json({'type':'preview','channels':[[.1,.2],[-.3,-.4]],'duration':.25})
        assert receive_type(sockets[0],'preview')['channels']==[[.1,.2],[-.3,-.4]]
        assert client.post(base+'/stop',headers=auth).status_code==200
        for person in people:
            data=b'independent-container-'+person['participant_id'].encode()
            endpoint=base+'/recordings/'+person['participant_id'];headers={'Authorization':'Bearer '+person['token'],'Content-Type':'audio/webm;codecs=opus','X-Checksum':hashlib.sha256(data).hexdigest(),'X-Created-At':'1001'}
            assert client.put(endpoint+'/chunks/0',params={'take_id':host['session_id']},headers=headers,content=data).status_code==200
            assert client.post(endpoint+'/finish',params={'take_id':host['session_id']},headers={'Authorization':headers['Authorization']},json={'chunk_count':1,'client_ms':2000,'duration_ms':1000}).status_code==200
            assert client.get(endpoint+'/audio',params={'take_id':host['session_id']},headers=auth).content==data
        state=client.get(base,headers=auth).json()
        assert state['status']=='completed'
        assert [r['channel_count'] for r in state['recordings']]==[1,2,1]
        assert client.get(base+'/analysis',headers=auth).status_code==200
