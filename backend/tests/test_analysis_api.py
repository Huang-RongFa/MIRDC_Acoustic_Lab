import hashlib
import os
import time
from uuid import uuid4

import numpy as np
import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.analysis import process_job
from backend.tests.test_analysis_signal import wav_bytes


def seed(client, app, formats):
    host = client.post('/api/rooms', json={'name':'A','record_as_host':True}).json()
    people = [host] + [client.post(f"/api/rooms/{host['room_code']}/join",json={'name':name}).json() for name in ('B','C')]
    sid = host['session_id']
    with app.state.db.transaction() as c:
        mid = c.execute("INSERT INTO public.machines(machine_code,machine_name) VALUES(%s,'analysis test') RETURNING machine_id",(str(uuid4()),)).fetchone()['machine_id']
        c.execute("UPDATE recording_sessions SET machine_id=%s,status='finalizing' WHERE id=%s",(mid,sid))
        for person,(rate,freqs) in zip(people,formats):
            data = wav_bytes(rate,freqs) if freqs else b'invalid audio'
            sha = hashlib.sha256(data).hexdigest()
            pid = person['participant_id']
            c.execute("UPDATE participant_recordings SET status='recording',actual_started_at=1000,mime_type='audio/webm',sample_rate=32000,requested_sample_rate=%s,requested_channel_count=2 WHERE session_id=%s AND participant_id=%s",(rate,sid,pid))
            c.execute("INSERT INTO audio_chunks(session_id,participant_id,chunk_index,mime_type,created_at,checksum,audio_data) VALUES(%s,%s,0,'audio/webm',1000,%s,%s)",(sid,pid,sha,data))
    return host, people


def finish(client, person):
    return client.post(f"/api/rooms/{person['room_code']}/recordings/{person['participant_id']}/finish",params={'take_id':person['session_id']},headers={'Authorization':'Bearer '+person['token']},json={'chunk_count':1,'client_ms':1300,'duration_ms':300})


def wait_result(client, base, headers, query=None):
    deadline = time.monotonic()+60
    while time.monotonic()<deadline:
        result=client.get(base,headers=headers,params=query).json()
        if result['status'] not in ('not_started','queued','running'):
            return result
        time.sleep(.15)
    raise AssertionError('analysis timed out')


@pytest.mark.parametrize('formats,count',[
    ([(48000,[1000])]*3,3),
    ([(48000,[1000]),(44100,[2000]),(48000,[3000])],3),
    ([(48000,[1000]),(44100,[2000,4000]),(48000,[3000])],4),
    ([(48000,[1000,5000]),(44100,[2000,6000]),(48000,[3000,7000])],6),
])
def test_real_pipeline_auto_queue_png_and_auth(formats,count):
    app = create_app(os.environ['TEST_DATABASE_URL'])
    with TestClient(app,client=('127.0.0.1',50000)) as client:
        host, people=seed(client,app,formats)
        headers={'Authorization':'Bearer '+host['token']}
        base=f"/api/v1/sessions/{host['session_id']}/analysis"
        for person in people:
            assert finish(client,person).status_code==200
        result=wait_result(client,base,headers)
        assert result['status']=='completed',result
        assert result['analyzable_track_count']==count
        assert result['completed_device_count']==3
        assert len(result['tracks'])==count
        assert [t['original_sample_rate'] for t in result['tracks']]==[rate for rate,freqs in formats for _ in freqs]
        assert all(t['analysis_sample_rate']==44100 and t['reported_sample_rate']==32000 for t in result['tracks'])
        assert len({t['track_id'] for t in result['tracks']})==count
        assert client.get(base).status_code==401
        outsider=client.post('/api/rooms',json={'name':'outside'}).json()
        for track in result['tracks']:
            for kind in ('spectrogram','mfcc'):
                url=track[kind+'_url']
                assert client.get(url,headers=headers).content.startswith(b'\x89PNG')
                assert client.get(url,headers={'Authorization':'Bearer '+outsider['token']}).status_code==403
        # Persisted result survives repeated GET; numerical matrices remain distinct.
        assert client.get(base,headers=headers).json()==result
        with app.state.db.transaction() as c:
            rows=c.execute("SELECT content FROM track_analysis_artifacts WHERE run_id=%s AND kind='matrices' ORDER BY track_id",(result['run_id'],)).fetchall()
            assert len(rows)==count
            if count>3:
                assert len({hashlib.sha256(row['content']).hexdigest() for row in rows})==count
            legacy=c.execute("SELECT count(*) AS n FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE'").fetchone()['n']
            assert legacy==28
        # Common interval applies to both plots and includes only real signal.
        response=client.post(base,headers=headers,json={'start_seconds':.1,'end_seconds':.25})
        assert response.status_code==202
        sliced=wait_result(client,base,headers,{'start_seconds':.1,'end_seconds':.25})
        assert sliced['time_range']==[.1,.25]
        assert all(.1<=t['valid_range'][0]<t['valid_range'][1]<=.25 for t in sliced['tracks'])
        assert client.post(base,headers=headers,json={'start_seconds':1,'end_seconds':.5}).status_code==422
        assert client.post(base,headers={'Authorization':'Bearer '+people[1]['token']},json={}).status_code==403


def test_missing_invalid_audio_actual_mono_and_restart():
    app=create_app(os.environ['TEST_DATABASE_URL'])
    with TestClient(app,client=('127.0.0.1',50000)) as client:
        host,people=seed(client,app,[(48000,[1000]),(44100,[]),(48000,[3000])])
        headers={'Authorization':'Bearer '+host['token']}
        base=f"/api/v1/sessions/{host['session_id']}/analysis"
        assert finish(client,people[0]).status_code==200
        assert finish(client,people[1]).status_code==200
        result=wait_result(client,base,headers)
        assert result['status']=='partial'
        assert len(result['tracks'])==1 and result['tracks'][0]['channel_label']=='Mono'
        assert {e['status'] for e in result['source_errors']}=={'missing','failed'}
        assert result['tracks'][0]['original_sample_rate']==48000
        # Replay a previously committed job (e.g. worker restart) is idempotent.
        with app.state.db.transaction() as c:
            job=c.execute('SELECT * FROM track_analysis_runs WHERE id=%s',(result['run_id'],)).fetchone()
        process_job(app.state.db,job)
        assert client.get(base,headers=headers).json()['status']=='partial'
    with TestClient(create_app(os.environ['TEST_DATABASE_URL']),client=('127.0.0.1',50000)) as restarted:
        assert restarted.get(base,headers=headers).json()['tracks'][0]['spectrogram_url']==result['tracks'][0]['spectrogram_url']


def test_recording_not_ready():
    with TestClient(create_app(os.environ['TEST_DATABASE_URL']),client=('127.0.0.1',50000)) as client:
        host=client.post('/api/rooms',json={'name':'host'}).json()
        base=f"/api/v1/sessions/{host['session_id']}/analysis"
        headers={'Authorization':'Bearer '+host['token']}
        assert client.get(base,headers=headers).json()['status']=='not_started'
        assert client.post(base,headers=headers,json={}).status_code==409
