import os
import secrets
import hashlib
import asyncio
import time
import math
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field, ConfigDict

from backend.db import Database
from backend.models import Conditions


def uid():
    return str(uuid4())


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


class Person(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    source_label: str | None = Field(default=None, pattern='^[ABC]$')


def create_app(database_url=None, countdown_seconds=3, acknowledgement_seconds=10, finalization_seconds=30):
    db = Database(database_url or os.environ.get('DATABASE_URL', 'postgresql://cnc_test@localhost:55432/cnc_lab'))
    peers = {}
    timers = set()
    attempts = {}

    def schedule(coroutine):
        task = asyncio.create_task(coroutine)
        timers.add(task)
        task.add_done_callback(timers.discard)

    @asynccontextmanager
    async def lifespan(app):
        # One server worker owns control delivery. A restart cannot resume capture.
        with db.control_lease():
            with db.transaction() as c:
                c.execute("UPDATE participant_recordings SET interrupted=true,status='interrupted',error='伺服器重啟，錄音可能中斷' WHERE session_id IN (SELECT id FROM recording_sessions WHERE status IN ('preparing','countdown','recording'))")
                c.execute("UPDATE recording_sessions SET status='interrupted',stopped_at=%s WHERE status IN ('preparing','countdown','recording')", (time.time()*1000,))
                c.execute('UPDATE room_participants SET mic=false,ready=false')
            yield
            for task in list(timers):
                task.cancel()
            await asyncio.gather(*timers, return_exceptions=True)

    app = FastAPI(title='CNC Acoustic Lab', lifespan=lifespan)
    app.state.db = db
    app.state.countdown_seconds = countdown_seconds

    def authorize(c, code, authorization, host=False):
        if not authorization or not authorization.startswith('Bearer '):
            raise HTTPException(401, '需要此房間的存取憑證')
        p = c.execute('SELECT p.* FROM room_participants p JOIN recording_rooms r ON r.id=p.room_id WHERE r.code=%s AND p.token_hash=%s', (code, digest(authorization[7:]))).fetchone()
        if not p:
            raise HTTPException(403, '房間憑證無效')
        if host and not p['is_host']:
            raise HTTPException(403, '只有主控者可操作')
        return p

    def snapshot(c, room_id):
        s = c.execute('SELECT * FROM recording_sessions WHERE room_id=%s', (room_id,)).fetchone()
        room = c.execute('SELECT code AS room_code,expires_at,closed_at FROM recording_rooms WHERE id=%s', (room_id,)).fetchone()
        participants = c.execute('SELECT id,source_label,name,is_host,mic,ready,error FROM room_participants WHERE room_id=%s ORDER BY source_label', (room_id,)).fetchall()
        for p in participants:
            p['connected'] = str(p['id']) in peers
        recordings = c.execute('''SELECT pr.*,p.source_label,a.byte_count AS byte_size,a.checksum AS asset_checksum,
            (SELECT count(*) FROM audio_chunks ch WHERE ch.session_id=pr.session_id AND ch.participant_id=pr.participant_id) AS received_chunks
            FROM participant_recordings pr JOIN room_participants p ON p.id=pr.participant_id
            LEFT JOIN audio_assets a ON a.session_id=pr.session_id AND a.participant_id=pr.participant_id
            WHERE pr.session_id=%s ORDER BY p.source_label''', (s['id'],)).fetchall()
        for r in recordings:
            r['missing_chunks'] = None if r['expected_chunks'] is None else max(0, r['expected_chunks'] - r['received_chunks'])
        return {**s, **room, 'participants': participants, 'recordings': recordings, 'server_now':time.time()*1000,
                'ready_count': sum(p['ready'] and p['mic'] and p['connected'] for p in participants)}

    def admission(c, room_id):
        room = c.execute('SELECT closed_at,expires_at<=now() AS expired FROM recording_rooms WHERE id=%s', (room_id,)).fetchone()
        if room['closed_at'] or room['expired']:
            raise HTTPException(410, '房間已關閉或過期，請建立新房間')

    async def broadcast(room_id, message):
        for peer in list(peers.values()):
            if peer['room_id'] == room_id:
                try:
                    await asyncio.wait_for(peer['ws'].send_json(jsonable_encoder(message)), 2)
                except (RuntimeError, WebSocketDisconnect, TimeoutError):
                    pass

    async def publish(room_id):
        with db.transaction() as c:
            state = snapshot(c, room_id)
        await broadcast(room_id, {'type':'state', 'state':state})

    async def check_acknowledgements(room_id, finalizing=False):
        await asyncio.sleep(finalization_seconds if finalizing else acknowledgement_seconds)
        with db.transaction() as c:
            s = c.execute('SELECT * FROM recording_sessions WHERE room_id=%s FOR UPDATE', (room_id,)).fetchone()
            if finalizing and s['status']=='finalizing':
                c.execute("UPDATE participant_recordings SET status='failed',error='停止後尚未完成上傳；請回原設備補傳' WHERE session_id=%s AND stopped_at IS NULL", (s['id'],))
                c.execute("UPDATE recording_sessions SET status='interrupted' WHERE id=%s", (s['id'],))
            elif not finalizing and s['status']=='recording':
                c.execute("UPDATE participant_recordings SET status='failed',error='未收到實際開始確認，不能確認此手機已錄音' WHERE session_id=%s AND actual_started_at IS NULL", (s['id'],))
            else:
                return
        await publish(room_id)

    async def countdown(room_id):
        await asyncio.sleep(countdown_seconds)
        with db.transaction() as c:
            s = c.execute('SELECT * FROM recording_sessions WHERE room_id=%s FOR UPDATE', (room_id,)).fetchone()
            if s['status'] != 'countdown':
                return
            state = snapshot(c, room_id)
            if state['ready_count'] != 3:
                c.execute("UPDATE recording_sessions SET status='waiting',starts_at=NULL WHERE id=%s", (s['id'],))
                event = {'type':'cancel', 'reason':'倒數期間有人離線'}
            else:
                now = time.time()*1000
                c.execute("UPDATE recording_sessions SET status='recording',started_at=%s WHERE id=%s", (now, s['id']))
                event = {'type':'start', 'session_id':str(s['id']), 'server_ms':now}
        await broadcast(room_id, event)
        await publish(room_id)
        if event['type']=='start':
            schedule(check_acknowledgements(room_id))

    async def prepare_timeout(room_id, attempt):
        await asyncio.sleep(10)
        if attempts.get(room_id) != attempt:
            return
        with db.transaction() as c:
            result = c.execute("UPDATE recording_sessions SET status='waiting' WHERE room_id=%s AND status='preparing' RETURNING id", (room_id,)).fetchone()
        if result:
            await broadcast(room_id, {'type':'cancel','reason':'裝置準備逾時，請重新就緒'})
            await publish(room_id)

    @app.post('/api/rooms', status_code=201)
    def create_room(body: Person):
        room, participant, session, token = uid(), uid(), uid(), secrets.token_urlsafe(32)
        with db.transaction() as c:
            for _ in range(32):
                code = ''.join(secrets.choice('ABCDEFGHJKLMNPQRSTUVWXYZ23456789') for _ in range(6))
                if c.execute('INSERT INTO recording_rooms(id,code) VALUES(%s,%s) ON CONFLICT(code) DO NOTHING RETURNING id', (room, code)).fetchone():
                    break
            else:
                raise HTTPException(503, '房間代碼暫時無法分配，請重試')
            c.execute('INSERT INTO room_participants(id,room_id,source_label,name,token_hash,is_host) VALUES(%s,%s,\'A\',%s,%s,true)', (participant, room, body.name, digest(token)))
            c.execute('INSERT INTO recording_sessions(id,room_id) VALUES(%s,%s)', (session, room))
            c.execute('INSERT INTO participant_recordings(session_id,participant_id,room_id) VALUES(%s,%s,%s)', (session, participant, room))
        return {'room_id': room, 'room_code': code, 'participant_id': participant, 'session_id': session, 'source_label': 'A', 'token': token, 'is_host': True}

    @app.post('/api/rooms/{code}/join', status_code=201)
    def join(code: str, body: Person, authorization: str | None = Header(None)):
        with db.transaction() as c:
            r = c.execute('SELECT * FROM recording_rooms WHERE code=%s FOR UPDATE', (code,)).fetchone()
            if not r:
                raise HTTPException(404, '找不到房間')
            admission(c, r['id'])
            s = c.execute('SELECT * FROM recording_sessions WHERE room_id=%s', (r['id'],)).fetchone()
            if authorization:
                p = authorize(c, code, authorization)
                return JSONResponse({'room_id':str(r['id']), 'room_code':code, 'participant_id':str(p['id']), 'session_id':str(s['id']), 'source_label':p['source_label'], 'token':authorization[7:], 'is_host':p['is_host']})
            if s['status'] != 'waiting':
                raise HTTPException(409, '錄音已開始，不能加入')
            used = {p['source_label'] for p in c.execute('SELECT source_label FROM room_participants WHERE room_id=%s', (r['id'],)).fetchall()}
            available = [label for label in 'BC' if label not in used]
            if not available:
                raise HTTPException(409, '房間已滿，最多三位錄音者；原設備請使用原憑證重新連線')
            label = body.source_label or available[0]
            if label in used:
                raise HTTPException(409, '此聲源已被使用')
            participant, token = uid(), secrets.token_urlsafe(32)
            c.execute('INSERT INTO room_participants(id,room_id,source_label,name,token_hash) VALUES(%s,%s,%s,%s,%s)', (participant, r['id'], label, body.name, digest(token)))
            c.execute('INSERT INTO participant_recordings(session_id,participant_id,room_id) VALUES(%s,%s,%s)', (s['id'], participant, r['id']))
        return {'room_id':str(r['id']), 'room_code': code, 'participant_id': participant, 'session_id': str(s['id']), 'source_label': label, 'token': token, 'is_host': False}

    @app.post('/api/rooms/{code}/close')
    async def close_room(code: str, authorization: str | None = Header(None)):
        with db.transaction() as c:
            p = authorize(c, code, authorization, host=True)
            s = c.execute('SELECT status FROM recording_sessions WHERE room_id=%s FOR UPDATE', (p['room_id'],)).fetchone()
            if s['status'] in ('preparing','countdown','recording','finalizing'):
                raise HTTPException(409, '請先停止錄音並確認上傳結果，再關閉房間')
            c.execute('UPDATE recording_rooms SET closed_at=COALESCE(closed_at,now()) WHERE id=%s', (p['room_id'],))
        await publish(p['room_id'])
        return {'ok':True}

    @app.get('/api/rooms/{code}')
    def get_room(code: str, authorization: str | None = Header(None)):
        with db.transaction() as c:
            p = authorize(c, code, authorization)
            return snapshot(c, p['room_id'])

    @app.put('/api/rooms/{code}/conditions')
    async def conditions(code: str, body: Conditions, authorization: str | None = Header(None)):
        with db.transaction() as c:
            p = authorize(c, code, authorization, host=True)
            s = c.execute('SELECT * FROM recording_sessions WHERE room_id=%s FOR UPDATE', (p['room_id'],)).fetchone()
            if s['status'] != 'waiting':
                raise HTTPException(409, '開始後不得更改加工條件')
            c.execute('UPDATE recording_sessions SET conditions=%s WHERE id=%s', (Jsonb(body.model_dump()), s['id']))
        await publish(p['room_id'])
        return {'ok':True}

    @app.post('/api/rooms/{code}/start')
    async def start(code: str, authorization: str | None = Header(None)):
        with db.transaction() as c:
            p = authorize(c, code, authorization, host=True)
            s = c.execute('SELECT * FROM recording_sessions WHERE room_id=%s FOR UPDATE', (p['room_id'],)).fetchone()
            admission(c, p['room_id'])
            state = snapshot(c, p['room_id'])
            if s['status'] != 'waiting' or state['ready_count'] != 3 or not s['conditions']:
                raise HTTPException(409, '需要三位錄音者就緒及加工條件')
            c.execute("UPDATE recording_sessions SET status='preparing' WHERE id=%s", (s['id'],))
            c.execute("UPDATE participant_recordings SET status='pending' WHERE session_id=%s", (s['id'],))
        attempt = uid()
        attempts[p['room_id']] = attempt
        await broadcast(p['room_id'], {'type':'prepare','session_id':str(s['id'])})
        await publish(p['room_id'])
        schedule(prepare_timeout(p['room_id'], attempt))
        return {'ok':True}

    @app.post('/api/rooms/{code}/stop')
    async def stop(code: str, authorization: str | None = Header(None)):
        with db.transaction() as c:
            p = authorize(c, code, authorization, host=True)
            s = c.execute('SELECT * FROM recording_sessions WHERE room_id=%s FOR UPDATE', (p['room_id'],)).fetchone()
            if s['status'] in ('finalizing','completed','interrupted'):
                return {'ok':True}
            if s['status'] not in ('recording','preparing','countdown'):
                raise HTTPException(409, '尚未開始')
            c.execute("UPDATE recording_sessions SET status='finalizing',stopped_at=%s WHERE id=%s", (time.time()*1000,s['id']))
        await broadcast(p['room_id'], {'type':'stop','session_id':str(s['id'])})
        await publish(p['room_id'])
        schedule(check_acknowledgements(p['room_id'], finalizing=True))
        return {'ok': True}

    @app.websocket('/api/rooms/{code}/ws')
    async def websocket(ws: WebSocket, code: str):
        await ws.accept()
        p = None
        try:
            auth = await asyncio.wait_for(ws.receive_json(), 10)
            if not isinstance(auth,dict) or auth.get('type')!='auth':
                raise ValueError('需要認證訊息')
            with db.transaction() as c:
                p = authorize(c, code, 'Bearer '+str(auth.get('token','')))
                pid = str(p['id'])
                if pid in peers:
                    await ws.close(4409, '此錄音者已有連線，請關閉另一個分頁')
                    p = None
                    return
                c.execute('UPDATE room_participants SET ready=false,mic=false,error=NULL WHERE id=%s', (p['id'],))
            peers[pid] = {'ws':ws,'room_id':p['room_id']}
            await publish(p['room_id'])
            preview_at = 0
            ping_at = 0
            last_ping = None
            while True:
                raw = await asyncio.wait_for(ws.receive_text(), 20)
                if len(raw) > 8192:
                    await ws.close(1009)
                    break
                import json
                m = json.loads(raw)
                if not isinstance(m,dict):
                    raise ValueError('訊息必須是物件')
                kind = m.get('type')
                if kind == 'ping':
                    if time.monotonic()-ping_at<1:
                        continue
                    ping_at=time.monotonic()
                    last_ping=(m.get('client_ms'),time.time()*1000)
                    await ws.send_json({'type':'pong','client_ms':last_ping[0], 'server_ms':last_ping[1]})
                    continue
                if kind == 'preview':
                    samples = m.get('samples')
                    if time.monotonic()-preview_at >= 0.18 and isinstance(samples,list) and 1 <= len(samples) <= 256 and all(type(x) in (int,float) and math.isfinite(x) and -1<=x<=1 for x in samples):
                        preview_at=time.monotonic()
                        await broadcast(p['room_id'], {'type':'preview','source_label':p['source_label'],'samples':samples,'server_ms':time.time()*1000})
                    continue
                start_countdown = False
                with db.transaction() as c:
                    s = c.execute('SELECT * FROM recording_sessions WHERE room_id=%s FOR UPDATE', (p['room_id'],)).fetchone()
                    if kind == 'mic' and s['status']=='waiting':
                        c.execute('UPDATE room_participants SET mic=%s,ready=false,error=NULL WHERE id=%s', (m.get('mic') is True,p['id']))
                    elif kind == 'ready' and s['status']=='waiting' and m.get('mic') is True:
                        c.execute('UPDATE room_participants SET ready=true,mic=true,error=NULL WHERE id=%s', (p['id'],))
                    elif kind == 'prepared' and s['status']=='preparing':
                        mime = m.get('mime_type','')
                        if mime not in ('audio/webm','audio/webm;codecs=opus','audio/mp4','audio/mp4;codecs=mp4a.40.2','audio/ogg;codecs=opus'):
                            raise ValueError('不支援的音訊格式')
                        rate, channels = m.get('sample_rate'), m.get('channel_count')
                        if (rate is not None and (type(rate) is not int or not 8000<=rate<=384000)) or (channels is not None and (type(channels) is not int or not 1<=channels<=32)):
                            raise ValueError('取樣資訊無效')
                        c.execute("UPDATE participant_recordings SET status='prepared',mime_type=%s,sample_rate=%s,channel_count=%s WHERE session_id=%s AND participant_id=%s", (mime,rate,channels,s['id'],p['id']))
                        count=c.execute("SELECT count(*) AS n FROM participant_recordings WHERE session_id=%s AND status='prepared'", (s['id'],)).fetchone()['n']
                        if count==3:
                            c.execute("UPDATE recording_sessions SET status='countdown',starts_at=%s WHERE id=%s", (time.time()*1000+countdown_seconds*1000,s['id']))
                            start_countdown=True
                    elif kind == 'started' and s['status'] in ('recording','finalizing','interrupted') and s['started_at'] is not None:
                        values=[float(m['client_ms']),float(m['performance_ms'])]
                        if not all(math.isfinite(x) and x>=0 for x in values):
                            raise ValueError('時間無效')
                        c.execute("UPDATE participant_recordings SET status=CASE WHEN interrupted THEN 'interrupted' ELSE %s END,error=CASE WHEN interrupted THEN error ELSE NULL END,actual_started_at=%s,start_perf_ms=%s,server_started_at=now() WHERE session_id=%s AND participant_id=%s AND actual_started_at IS NULL AND mime_type IS NOT NULL", ('recording' if s['status']=='recording' else 'uploading',*values,s['id'],p['id']))
                    elif kind == 'error':
                        error=str(m.get('message','裝置錯誤'))[:300]
                        c.execute('UPDATE room_participants SET ready=false,mic=false,error=%s WHERE id=%s', (error,p['id']))
                        if s['status'] in ('recording','finalizing'):
                            c.execute("UPDATE participant_recordings SET interrupted=true,status='interrupted',error=%s WHERE session_id=%s AND participant_id=%s AND status NOT IN ('stored','interrupted')", (error,s['id'],p['id']))
                    elif kind == 'clock':
                        if last_ping is None or (m.get('client_sent_ms'),m.get('server_received_ms'))!=last_ping:
                            continue
                        last_ping=None
                        values=[float(m[k]) for k in ('client_sent_ms','server_received_ms','client_received_ms','performance_ms')]
                        if not all(math.isfinite(x) and x>=0 for x in values):
                            raise ValueError('時間無效')
                        c.execute('INSERT INTO device_clock_observations(session_id,participant_id,client_sent_ms,server_received_ms,client_received_ms,performance_ms) VALUES(%s,%s,%s,%s,%s,%s)', (s['id'],p['id'],*values))
                if start_countdown:
                    schedule(countdown(p['room_id']))
                await publish(p['room_id'])
        except TimeoutError:
            try:
                await ws.close(4008, '連線逾時，請重新連線')
            except (RuntimeError, WebSocketDisconnect):
                pass
        except (WebSocketDisconnect, HTTPException, ValueError, KeyError, TypeError):
            try:
                await ws.close(4400)
            except (RuntimeError, WebSocketDisconnect):
                pass
        finally:
            if p and peers.get(str(p['id']),{}).get('ws') is ws:
                peers.pop(str(p['id']),None)
                with db.transaction() as c:
                    c.execute('UPDATE room_participants SET ready=false,error=%s WHERE id=%s', ('連線中斷，無法確認此手機是否持續錄音；請回原頁面重新連線',p['id']))
                await publish(p['room_id'])

    app.state.authorize = authorize
    app.state.publish = publish
    from backend.audio import register_audio
    register_audio(app)
    from backend.catalog import register_catalog
    register_catalog(app)

    return app


app = create_app()
