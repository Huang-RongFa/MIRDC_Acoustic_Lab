import os
import pytest
import psycopg
from uuid import uuid4
from fastapi.testclient import TestClient
from backend.app import create_app


def test_legacy_tables_are_preserved_and_cross_room_recordings_are_rejected():
    url=os.environ['TEST_DATABASE_URL']
    with TestClient(create_app(url)) as client:
        first=client.post('/api/rooms',json={'name':'first'}).json()
        second=client.post('/api/rooms',json={'name':'second'}).json()
        with psycopg.connect(url) as c:
            legacy=c.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE'").fetchone()[0]
            assert legacy==28
            room=c.execute('SELECT room_id FROM mobile_capture.recording_sessions WHERE id=%s',(first['session_id'],)).fetchone()[0]
            with pytest.raises(psycopg.errors.ForeignKeyViolation):
                with c.transaction():
                    c.execute('INSERT INTO mobile_capture.participant_recordings(session_id,participant_id,room_id) VALUES(%s,%s,%s)',(first['session_id'],second['participant_id'],room))
            with pytest.raises(psycopg.errors.UniqueViolation):
                with c.transaction():
                    c.execute("INSERT INTO mobile_capture.room_participants(id,room_id,source_label,name,token_hash) VALUES(%s,%s,'A','duplicate',%s)",(uuid4(),room,str(uuid4())))


def test_chunk_identity_and_size_are_queryable_without_custom_search_path():
    import hashlib
    url=os.environ['TEST_DATABASE_URL']
    with TestClient(create_app(url)) as client:
        host=client.post('/api/rooms',json={'name':'A'}).json()
        with psycopg.connect(url) as c:
            data=b'transport-fixture-not-real-audio'
            c.execute('INSERT INTO mobile_capture.audio_chunks(session_id,participant_id,chunk_index,mime_type,created_at,checksum,audio_data) VALUES(%s,%s,0,%s,1000,%s,%s)',(host['session_id'],host['participant_id'],'audio/webm',hashlib.sha256(data).hexdigest(),data))
            row=c.execute('SELECT ch.source_label,ch.byte_size,ch.participant_recording_id=pr.participant_recording_id FROM mobile_capture.audio_chunks ch JOIN mobile_capture.participant_recordings pr USING(session_id,participant_id) WHERE ch.session_id=%s',(host['session_id'],)).fetchone()
            assert row==('A',len(data),True)
