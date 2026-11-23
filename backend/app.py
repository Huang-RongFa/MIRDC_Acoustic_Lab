import os
import secrets
import hashlib
import asyncio
import time
import math
from contextlib import asynccontextmanager
from uuid import UUID, uuid4

from fastapi import FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field, ConfigDict

from backend.network import InternalNetwork
from backend.db import Database
from backend.schema import DEFAULT_DATABASE_URL, check_schema
from backend.models import Conditions
from backend.capture_protocol import capture_settings, preview_channels


def uid():
    return str(uuid4())


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


class Person(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class RoomConfig(BaseModel):
    required_recorder_count: int = Field(ge=1, le=5)


class RoomCreation(Person, RoomConfig):
    record_as_host: bool = False
    required_recorder_count: int = Field(default=3, ge=1, le=5)


def create_app(database_url=None, countdown_seconds=3, acknowledgement_seconds=10, finalization_seconds=30):
    db = Database(database_url or os.environ.get('DATABASE_URL') or DEFAULT_DATABASE_URL)
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
                check_schema(c)
                c.execute("UPDATE participant_recordings SET interrupted=true,status='interrupted',error='伺服器重啟，錄音可能中斷' WHERE session_id IN (SELECT id FROM recording_sessions WHERE status IN ('preparing','countdown','recording'))")
                c.execute("UPDATE recording_sessions SET status='interrupted',stopped_at=%s WHERE status IN ('preparing','countdown','recording')", (time.time()*1000,))
                c.execute('UPDATE room_participants SET revoked=true,source_label=NULL WHERE leaving AND NOT revoked')
                c.execute('UPDATE room_participants SET mic=false,ready=false')
                c.execute("UPDATE track_analysis_runs SET status='queued' WHERE status='running'")
            from backend.analysis import worker
            analysis_stop = asyncio.Event()
            analysis_task = asyncio.create_task(worker(db, analysis_stop))
            try:
                yield
            finally:
                analysis_stop.set()
                await analysis_task
                for task in list(timers):
                    task.cancel()
                await asyncio.gather(*timers, return_exceptions=True)

    app = FastAPI(title='CNC Acoustic Lab', lifespan=lifespan)
    app.add_middleware(InternalNetwork)
    app.state.db = db
    app.state.countdown_seconds = countdown_seconds

    @app.get('/api/health')
    def health():
        with db.transaction() as c:
            c.execute('SELECT 1')
        return {'status':'ok','service':'cnc-acoustic-lab'}

    def authorize(c, code, authorization, host=False):
        if not authorization or not authorization.startswith('Bearer '):
            raise HTTPException(401, '需要此房間的存取憑證')
        p = c.execute('SELECT p.* FROM room_participants p JOIN recording_rooms r ON r.id=p.room_id WHERE r.code=%s AND p.token_hash=%s AND NOT p.revoked', (code, digest(authorization[7:]))).fetchone()
        if not p:
            raise HTTPException(403, '房間憑證無效')
        if host and not p['is_host']:
            raise HTTPException(403, '只有主控者可操作')
        return p

    def snapshot(c, room_id, take_id=None):
        s = c.execute('SELECT * FROM recording_sessions WHERE room_id=%s AND (%s::uuid IS NULL OR id=%s) ORDER BY created_at DESC LIMIT 1', (room_id,take_id,take_id)).fetchone()
        if not s:
            raise HTTPException(404,'找不到錄音批次')
        room = c.execute('SELECT code AS room_code,expires_at,closed_at,closing,event_version,assignment_version,required_recorder_count FROM recording_rooms WHERE id=%s', (room_id,)).fetchone()
        participants = c.execute('SELECT id,recorder_id,leaving,source_label,name,is_host,mic,microphone_permission,ready,error FROM room_participants WHERE room_id=%s AND NOT revoked ORDER BY source_label', (room_id,)).fetchall()
        for p in participants:
            p['capture_settings'] = peers.get(str(p['id']),{}).get('capture_settings')
            p['connected'] = str(p['id']) in peers
            p['ready'] = bool(p['source_label'] and p['connected'] and p['mic'] and not p['error'] and not p['leaving'])
            p.update(participant_id=p['id'],source_position=p['source_label'],position_order='ABCDE'.index(p['source_label'])+1 if p['source_label'] else None,
                     network_connected=p['connected'],microphone_active=p['mic'],recorder_ready=p['ready'],is_ready=p['ready'])
        recordings = c.execute('''SELECT pr.*,pr.source_position AS source_label,a.byte_count AS byte_size,a.checksum AS asset_checksum,
            (SELECT count(*) FROM audio_chunks ch WHERE ch.session_id=pr.session_id AND ch.participant_id=pr.participant_id) AS received_chunks
            FROM participant_recordings pr JOIN room_participants p ON p.id=pr.participant_id
            LEFT JOIN audio_assets a ON a.session_id=pr.session_id AND a.participant_id=pr.participant_id
            WHERE pr.session_id=%s ORDER BY pr.source_position''', (s['id'],)).fetchall()
        tracks={str(r['participant_id']):r for r in recordings}
        for member in participants:
            track=tracks.get(str(member['id']),{})
            member['recording_active']=track.get('status')=='recording'
            member['upload_status']=track.get('status')
        for r in recordings:
            r['missing_chunks'] = None if r['expected_chunks'] is None else max(0, r['expected_chunks'] - r['received_chunks'])
            r['capture_server_ms'] = None
            r['clock_uncertainty_ms'] = None
            if r['start_perf_ms'] is not None:
                observation = c.execute('''SELECT * FROM device_clock_observations
                    WHERE session_id=%s AND participant_id=%s
                    AND abs(performance_ms-%s)<30000
                    AND abs(client_received_ms-%s)<30000
                    AND client_received_ms>=client_sent_ms
                    AND client_received_ms-client_sent_ms<2000
                    ORDER BY client_received_ms-client_sent_ms LIMIT 1''',
                    (s['id'],r['participant_id'],r['start_perf_ms'],r['actual_started_at'])).fetchone()
                if observation:
                    half_rtt = (observation['client_received_ms']-observation['client_sent_ms'])/2
                    r['capture_server_ms'] = observation['server_received_ms']+half_rtt+r['start_perf_ms']-observation['performance_ms']
                    r['clock_uncertainty_ms'] = half_rtt
        return {**s, **room, 'take_id':s['id'], 'participants': participants, 'recordings': recordings, 'server_now':time.time()*1000,
                'required_recorder_count':len(recordings) if s['status']!='waiting' else room['required_recorder_count'],
                'ready_count': sum(p['ready'] and p['mic'] and p['connected'] for p in participants if p['source_label'])}

    def admission(c, room_id):
        room = c.execute('SELECT closed_at,closing,expires_at<=now() AS expired FROM recording_rooms WHERE id=%s', (room_id,)).fetchone()
        if room['closed_at'] or room['closing'] or room['expired']:
            raise HTTPException(410, '房間已關閉或過期，請建立新房間')

    async def broadcast(room_id, message):
        for peer in list(peers.values()):
            if peer['room_id'] == room_id:
                try:
                    await asyncio.wait_for(peer['ws'].send_json(jsonable_encoder(message)), 2)
                except (RuntimeError, WebSocketDisconnect, TimeoutError, OSError):
                    pass

    async def publish(room_id):
        departed=[]
        with db.transaction() as c:
            c.execute('UPDATE recording_rooms SET event_version=event_version+1 WHERE id=%s',(room_id,))
            state = snapshot(c, room_id)
            if state['status']!='waiting':
                for track in state['recordings']:
                    if track['asset_checksum'] or (state['status'] in ('finalizing','interrupted') and track['actual_started_at'] is None):
                        row=c.execute('UPDATE room_participants SET revoked=true,source_label=NULL,ready=false WHERE id=%s AND leaving AND NOT revoked RETURNING id',(track['participant_id'],)).fetchone()
                        if row:
                            departed.append(str(row['id']))
                if departed:
                    c.execute('UPDATE recording_rooms SET assignment_version=assignment_version+1 WHERE id=%s',(room_id,))
                    state=snapshot(c, room_id)
            if state['closing'] and not state['closed_at'] and (state['status']=='waiting' or all(r['asset_checksum'] for r in state['recordings'])):
                c.execute('UPDATE recording_rooms SET closed_at=now() WHERE id=%s AND closed_at IS NULL',(room_id,))
                c.execute('UPDATE room_participants SET revoked=true WHERE room_id=%s',(room_id,))
                state['closed_at']=True
        for participant_id in departed:
            peer=peers.get(participant_id)
            if peer and peer['ws'].application_state.name=='CONNECTED':
                await peer['ws'].close(4410,'已退出房間')
        if state['closed_at']:
            await broadcast(room_id, {'type':'room_closed'})
            for peer in list(peers.values()):
                if peer['room_id']==room_id and peer['ws'].application_state.name=='CONNECTED':
                    await peer['ws'].close(4410,'房間已關閉')
            return
        await broadcast(room_id, {'type':'state', 'state':state})

    async def check_acknowledgements(room_id, take_id, finalizing=False):
        await asyncio.sleep(finalization_seconds if finalizing else acknowledgement_seconds)
        with db.transaction() as c:
            s = c.execute('SELECT * FROM recording_sessions WHERE room_id=%s ORDER BY created_at DESC LIMIT 1 FOR UPDATE', (room_id,)).fetchone()
            if s['id']!=take_id:
                return
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
            s = c.execute('SELECT * FROM recording_sessions WHERE room_id=%s ORDER BY created_at DESC LIMIT 1 FOR UPDATE', (room_id,)).fetchone()
            if s['status'] != 'countdown':
                return
            state = snapshot(c, room_id)
            if state['ready_count'] != state['required_recorder_count']:
                c.execute("UPDATE recording_sessions SET status='waiting',starts_at=NULL WHERE id=%s", (s['id'],))
                event = {'type':'cancel', 'reason':'倒數期間有人離線'}
            else:
                now = time.time()*1000
                c.execute("UPDATE recording_sessions SET status='recording',started_at=starts_at WHERE id=%s", (s['id'],))
                event = {'type':'start', 'session_id':str(s['id']), 'server_ms':now}
        await broadcast(room_id, event)
        await publish(room_id)
        if event['type']=='start':
            schedule(check_acknowledgements(room_id,s['id']))

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
    def create_room(body: RoomCreation):
        room, participant, session, token = uid(), uid(), uid(), secrets.token_urlsafe(32)
        position = 'A' if body.record_as_host else None
        with db.transaction() as c:
            for _ in range(32):
                code = ''.join(secrets.choice('ABCDEFGHJKLMNPQRSTUVWXYZ23456789') for _ in range(6))
                if c.execute('INSERT INTO recording_rooms(id,code,required_recorder_count) VALUES(%s,%s,%s) ON CONFLICT(code) DO NOTHING RETURNING id', (room, code, body.required_recorder_count)).fetchone():
                    break
            else:
                raise HTTPException(503, '房間代碼暫時無法分配，請重試')
            c.execute('INSERT INTO room_participants(id,room_id,source_label,name,token_hash,is_host) VALUES(%s,%s,%s,%s,%s,true)', (participant, room, position, body.name, digest(token)))
            c.execute('INSERT INTO recording_sessions(id,room_id) VALUES(%s,%s)', (session, room))
            if position:
                c.execute('INSERT INTO participant_recordings(session_id,participant_id,room_id,source_position) VALUES(%s,%s,%s,%s)',(session,participant,room,position))
        return {'room_id': room, 'room_code': code, 'participant_id': participant, 'session_id': session, 'source_label': position, 'token': token, 'is_host': True}

    @app.post('/api/rooms/{code}/join', status_code=201)
    async def join(code: str, body: Person, authorization: str | None = Header(None)):
        with db.transaction() as c:
            r = c.execute('SELECT * FROM recording_rooms WHERE code=%s FOR UPDATE', (code,)).fetchone()
            if not r:
                raise HTTPException(404, '找不到房間')
            admission(c, r['id'])
            s = c.execute('SELECT * FROM recording_sessions WHERE room_id=%s ORDER BY created_at DESC LIMIT 1', (r['id'],)).fetchone()
            if authorization:
                p = authorize(c, code, authorization)
                return JSONResponse({'room_id':str(r['id']), 'room_code':code, 'participant_id':str(p['id']), 'session_id':str(s['id']), 'source_label':p['source_label'], 'token':authorization[7:], 'is_host':p['is_host']})
            if s['status'] != 'waiting':
                raise HTTPException(409, '錄音已開始，不能加入')
            used = {p['source_label'] for p in c.execute('SELECT source_label FROM room_participants WHERE room_id=%s AND NOT revoked', (r['id'],)).fetchall()}
            available = [label for label in 'ABCDE'[:r['required_recorder_count']] if label not in used]
            if not available:
                raise HTTPException(409, '房間已滿，已達設定人數；原設備請使用原憑證重新連線')
            label = available[0]
            if label in used:
                raise HTTPException(409, '此聲源已被使用')
            participant, token = uid(), secrets.token_urlsafe(32)
            c.execute('INSERT INTO room_participants(id,room_id,source_label,name,token_hash) VALUES(%s,%s,%s,%s,%s)', (participant, r['id'], label, body.name, digest(token)))
            c.execute('INSERT INTO participant_recordings(session_id,participant_id,room_id,source_position) VALUES(%s,%s,%s,%s)', (s['id'], participant, r['id'], label))
            c.execute('UPDATE recording_rooms SET assignment_version=assignment_version+1 WHERE id=%s',(r['id'],))
        await publish(r['id'])
        return {'room_id':str(r['id']), 'room_code': code, 'participant_id': participant, 'session_id': str(s['id']), 'source_label': label, 'token': token, 'is_host': False}

    @app.post('/api/rooms/{code}/next')
    async def next_take(code: str, authorization: str | None = Header(None)):
        with db.transaction() as c:
            p = authorize(c, code, authorization, host=True)
            room_id = p['room_id']
            c.execute('SELECT id FROM recording_rooms WHERE id=%s FOR UPDATE', (room_id,))
            admission(c, room_id)
            state = snapshot(c, room_id)
            if state['status'] not in ('completed','interrupted') or any(r['asset_checksum'] is None for r in state['recordings']):
                raise HTTPException(409, '請先完成本次音訊封存')
            take = uid()
            c.execute('INSERT INTO recording_sessions(id,room_id,machine_id,conditions) VALUES(%s,%s,%s,%s)', (take,room_id,state['machine_id'],Jsonb(state['conditions'])))
            c.execute('INSERT INTO participant_recordings(session_id,participant_id,room_id,source_position) SELECT %s,id,room_id,source_label FROM room_participants WHERE room_id=%s AND source_label IS NOT NULL AND NOT revoked',(take,room_id))
            c.execute('UPDATE room_participants SET ready=false WHERE room_id=%s',(room_id,))
        await publish(room_id)
        return {'take_id':take}

    async def expire_departure(room_id,target):
        await asyncio.sleep(finalization_seconds)
        with db.transaction() as c:
            c.execute('SELECT id FROM recording_rooms WHERE id=%s FOR UPDATE',(room_id,))
            row=c.execute('UPDATE room_participants SET revoked=true,source_label=NULL,ready=false WHERE id=%s AND leaving AND NOT revoked RETURNING id',(target,)).fetchone()
            if not row:
                return
            c.execute('UPDATE recording_rooms SET assignment_version=assignment_version+1 WHERE id=%s',(room_id,))
        peer=peers.get(target)
        if peer and peer['ws'].application_state.name=='CONNECTED':
            await peer['ws'].close(4410,'已退出房間')
        await publish(room_id)

    @app.delete('/api/rooms/{code}/participants/{participant_id}')
    @app.post('/api/rooms/{code}/leave')
    async def leave(code: str, participant_id: str | None = None, authorization: str | None = Header(None)):
        with db.transaction() as c:
            actor = authorize(c, code, authorization, host=participant_id is not None)
            room_id = actor['room_id']
            c.execute('SELECT id FROM recording_rooms WHERE id=%s FOR UPDATE',(room_id,))
            state = snapshot(c, room_id)
            target = str(participant_id or actor['id'])
            track=next((track for track in state['recordings'] if str(track['participant_id'])==target),None)
            pending=state['status']!='waiting' and track and not track['asset_checksum']
            if pending:
                if not c.execute('UPDATE room_participants SET leaving=true WHERE room_id=%s AND id=%s AND NOT revoked AND NOT is_host RETURNING id',(room_id,target)).fetchone():
                    raise HTTPException(404,'找不到有效錄音者')
                c.execute("UPDATE participant_recordings SET interrupted=true WHERE session_id=%s AND participant_id=%s",(state['id'],target))
            else:
                if not c.execute('UPDATE room_participants SET revoked=true,source_label=NULL,ready=false WHERE room_id=%s AND id=%s AND NOT is_host AND NOT revoked RETURNING id',(room_id,target)).fetchone():
                    raise HTTPException(404, '找不到有效錄音者')
                if state['status']=='waiting':
                    c.execute('''DELETE FROM device_clock_observations AS clock USING participant_recordings AS recording
                        WHERE clock.session_id=recording.session_id AND clock.participant_id=recording.participant_id
                        AND recording.session_id=%s AND recording.participant_id=%s AND recording.actual_started_at IS NULL''',(state['id'],target))
                    c.execute("DELETE FROM participant_recordings WHERE session_id=%s AND participant_id=%s AND actual_started_at IS NULL",(state['id'],target))
                c.execute('UPDATE recording_rooms SET assignment_version=assignment_version+1 WHERE id=%s',(room_id,))
        peer = peers.get(target)
        if pending:
            schedule(expire_departure(room_id,target))
            if peer:
                await peer['ws'].send_json({'type':'stop_personal'})
            await publish(room_id)
            return {'pending_upload':True}
        if peer:
            await peer['ws'].close(4410,'已退出房間')
        await publish(room_id)
        return {'ok':True}

    @app.post('/api/rooms/{code}/close')
    async def close_room(code: str, authorization: str | None = Header(None)):
        with db.transaction() as c:
            p = authorize(c, code, authorization, host=True)
            s = c.execute('SELECT status FROM recording_sessions WHERE room_id=%s ORDER BY created_at DESC LIMIT 1 FOR UPDATE', (p['room_id'],)).fetchone()
            c.execute('UPDATE recording_rooms SET closing=true WHERE id=%s',(p['room_id'],))
            if s['status'] in ('preparing','countdown'):
                c.execute("UPDATE recording_sessions SET status='waiting',starts_at=NULL WHERE room_id=%s AND status IN ('preparing','countdown')",(p['room_id'],))
                s['status']='waiting'
        if s['status'] in ('preparing','countdown','recording'):
            await stop(code, authorization)
        elif s['status']=='finalizing':
            await broadcast(p['room_id'], {'type':'stop'})
        await publish(p['room_id'])
        return {'ok':True}

    @app.get('/api/rooms/{code}/takes')
    def takes(code: str, authorization: str | None = Header(None)):
        with db.transaction() as c:
            p=authorize(c,code,authorization)
            return {'items':c.execute('SELECT id,created_at FROM recording_sessions WHERE room_id=%s ORDER BY created_at DESC',(p['room_id'],)).fetchall()}

    @app.get('/api/rooms/{code}/state')
    @app.get('/api/rooms/{code}')
    def get_room(code: str, take_id: UUID | None = None, authorization: str | None = Header(None)):
        with db.transaction() as c:
            p = authorize(c, code, authorization)
            return snapshot(c, p['room_id'],take_id)

    @app.post('/api/rooms/{code}/ready')
    async def ready(code: str, authorization: str | None = Header(None)):
        with db.transaction() as c:
            p=authorize(c,code,authorization)
            admission(c,p['room_id'])
            state=snapshot(c,p['room_id'])
            if not p['source_label'] or not p['mic'] or str(p['id']) not in peers or state['status']!='waiting':
                raise HTTPException(409,'請先連接麥克風並等待房間就緒')
            c.execute('UPDATE room_participants SET ready=true WHERE id=%s',(p['id'],))
        await publish(p['room_id'])
        return {'ok':True}

    @app.patch('/api/rooms/{code}/config')
    async def configure(code: str, body: RoomConfig, authorization: str | None = Header(None)):
        with db.transaction() as c:
            p = authorize(c, code, authorization, host=True)
            room_id = p['room_id']
            c.execute('SELECT id FROM recording_rooms WHERE id=%s FOR UPDATE', (room_id,))
            admission(c, room_id)
            state = snapshot(c, room_id)
            positions = 'ABCDE'[:body.required_recorder_count]
            if state['status'] != 'waiting' or any(member['source_label'] and member['source_label'] not in positions for member in state['participants']):
                raise HTTPException(409, '請在等待階段調整名單後再修改人數')
            c.execute('UPDATE recording_rooms SET assignment_version=assignment_version+1,required_recorder_count=%s WHERE id=%s', (body.required_recorder_count, room_id))
        await publish(room_id)
        return {'ok': True}

    @app.get('/api/machines')
    def machines(authorization: str | None = Header(None)):
        with db.transaction() as c:
            if not authorization or not authorization.startswith('Bearer ') or not c.execute(
                'SELECT 1 FROM room_participants p JOIN recording_rooms r ON r.id=p.room_id WHERE token_hash=%s AND NOT p.revoked AND closed_at IS NULL AND expires_at>now()', (digest(authorization[7:]),)
            ).fetchone():
                raise HTTPException(403, '需要有效的房間憑證')
            return {'items': c.execute('SELECT machine_id,machine_code,machine_name,machine_type,model AS machine_model FROM public.machines WHERE is_active ORDER BY machine_code').fetchall()}

    def machine_snapshot(c, machine_id):
        machine = c.execute('SELECT machine_code,machine_name,model AS machine_model,machine_type FROM public.machines WHERE machine_id=%s AND is_active FOR SHARE', (machine_id,)).fetchone()
        if not machine:
            raise HTTPException(422, '請先選擇機台')
        return machine

    @app.put('/api/rooms/{code}/conditions')
    async def conditions(code: str, body: Conditions, authorization: str | None = Header(None)):
        with db.transaction() as c:
            p = authorize(c, code, authorization, host=True)
            s = c.execute('SELECT * FROM recording_sessions WHERE room_id=%s ORDER BY created_at DESC LIMIT 1 FOR UPDATE', (p['room_id'],)).fetchone()
            if s['status'] != 'waiting':
                raise HTTPException(409, '開始後不得更改加工條件')
            values = body.model_dump(mode='json')
            machine_id = body.machine_id
            if machine_id is None:
                code_text = (body.machine_code or '').strip()
                if not code_text:
                    raise HTTPException(422, '請輸入或選擇機台')
                matches = c.execute('SELECT machine_code FROM public.machines WHERE machine_name=%s AND is_active AND NOT EXISTS (SELECT 1 FROM public.machines WHERE machine_code=%s) LIMIT 2', (code_text,code_text)).fetchall()
                if len(matches)>1:
                    raise HTTPException(422, '多台機台使用相同名稱，請輸入機台編號')
                if matches:
                    code_text = matches[0]['machine_code']
                c.execute('INSERT INTO public.machines(machine_code,machine_name) VALUES(%s,%s) ON CONFLICT(machine_code) DO NOTHING', (code_text,code_text))
                row = c.execute('SELECT machine_id FROM public.machines WHERE machine_code=%s AND is_active FOR SHARE', (code_text,)).fetchone()
                if not row:
                    raise HTTPException(422, '此機台已停用')
                machine_id = row['machine_id']
            values['machine_id'] = str(machine_id)
            values.update(machine_snapshot(c, machine_id))
            c.execute('UPDATE recording_sessions SET machine_id=%s,conditions=%s WHERE id=%s', (machine_id, Jsonb(values), s['id']))
        await publish(p['room_id'])
        return {'ok':True}

    @app.post('/api/rooms/{code}/start')
    async def start(code: str, authorization: str | None = Header(None)):
        with db.transaction() as c:
            p = authorize(c, code, authorization, host=True)
            c.execute('SELECT id FROM recording_rooms WHERE id=%s FOR UPDATE',(p['room_id'],))
            admission(c, p['room_id'])
            s = c.execute('SELECT * FROM recording_sessions WHERE room_id=%s ORDER BY created_at DESC LIMIT 1 FOR UPDATE', (p['room_id'],)).fetchone()
            state = snapshot(c, p['room_id'])
            machine = machine_snapshot(c, s['machine_id'])
            if s['status'] in ('preparing','countdown','recording'):
                return {'ok':True,'take_id':s['id']}
            if s['status'] != 'waiting' or state['ready_count'] != state['required_recorder_count'] or not s['conditions']:
                raise HTTPException(409, '需要全體錄音者就緒')
            c.execute("UPDATE recording_sessions SET status='preparing', conditions=conditions || %s WHERE id=%s", (Jsonb(machine), s['id']))
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
            s = c.execute('SELECT * FROM recording_sessions WHERE room_id=%s ORDER BY created_at DESC LIMIT 1 FOR UPDATE', (p['room_id'],)).fetchone()
            if s['status'] in ('finalizing','completed','interrupted'):
                return {'ok':True}
            if s['status'] not in ('recording','preparing','countdown'):
                raise HTTPException(409, '尚未開始')
            c.execute("UPDATE recording_sessions SET status='finalizing',stopped_at=%s WHERE id=%s", (time.time()*1000,s['id']))
        await broadcast(p['room_id'], {'type':'stop','session_id':str(s['id'])})
        await publish(p['room_id'])
        schedule(check_acknowledgements(p['room_id'],s['id'], finalizing=True))
        return {'ok': True}

    @app.websocket('/ws/rooms/{code}')
    @app.websocket('/api/rooms/{code}/ws')
    async def websocket(ws: WebSocket, code: str):
        await ws.accept()
        p = None
        try:
            auth = await asyncio.wait_for(ws.receive_json(), 10)
            if not isinstance(auth,dict) or auth.get('type')!='auth':
                raise ValueError('需要認證訊息')
            with db.transaction() as c:
                closed = c.execute('SELECT closed_at FROM recording_rooms WHERE code=%s',(code,)).fetchone()
                if closed and closed['closed_at']:
                    await ws.close(4410,'房間已關閉')
                    return
                try:
                    p = authorize(c, code, 'Bearer '+str(auth.get('token','')))
                except HTTPException:
                    await ws.close(4410,'房間憑證無效')
                    return
                if p['leaving']:
                    await ws.close(4410,'已退出房間')
                    return
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
                with db.transaction() as c:
                    p=authorize(c,code,'Bearer '+str(auth.get('token','')))
                if not p['source_label']:
                    continue
                if kind == 'preview':
                    channels = preview_channels(m)
                    if time.monotonic()-preview_at >= 0.18 and channels is not None:
                        duration=m.get('duration')
                        if type(duration) not in (int,float) or not 0 < duration <= 1:
                            duration=None
                        preview_at=time.monotonic()
                        await broadcast(p['room_id'], {'type':'preview','source_label':p['source_label'],'samples':channels[0],'channels':channels,'duration':duration,'server_ms':time.time()*1000})
                    continue
                start_countdown = False
                with db.transaction() as c:
                    s = c.execute('SELECT * FROM recording_sessions WHERE room_id=%s ORDER BY created_at DESC LIMIT 1 FOR UPDATE', (p['room_id'],)).fetchone()
                    if kind == 'capture_settings' and s['status']=='waiting':
                        peers[str(p['id'])]['capture_settings'] = capture_settings(m)
                    elif kind == 'mic' and s['status']=='waiting':
                        c.execute("UPDATE room_participants SET mic=%s,microphone_permission='granted',ready=false,error=NULL WHERE id=%s", (m.get('mic') is True,p['id']))
                    elif kind == 'ready' and s['status']=='waiting' and m.get('mic') is True:
                        c.execute('UPDATE room_participants SET ready=true,error=NULL WHERE id=%s AND mic', (p['id'],))
                    elif kind == 'prepared' and s['status']=='preparing':
                        mime = m.get('mime_type','')
                        if mime not in ('audio/webm','audio/webm;codecs=opus','audio/mp4','audio/mp4;codecs=mp4a.40.2','audio/ogg;codecs=opus'):
                            raise ValueError('不支援的音訊格式')
                        rate, channels = m.get('sample_rate'), m.get('channel_count')
                        if (rate is not None and (type(rate) is not int or not 8000<=rate<=384000)) or (channels is not None and (type(channels) is not int or not 1<=channels<=32)):
                            raise ValueError('取樣資訊無效')
                        c.execute("UPDATE participant_recordings SET status='prepared',mime_type=%s,sample_rate=%s,channel_count=%s WHERE session_id=%s AND participant_id=%s", (mime,rate,channels,s['id'],p['id']))
                        requested = peers[str(p['id'])].get('capture_settings') or {}
                        c.execute('UPDATE participant_recordings SET requested_sample_rate=%s,requested_channel_count=%s WHERE session_id=%s AND participant_id=%s', (requested.get('requested_sample_rate'),requested.get('requested_channel_count'),s['id'],p['id']))
                        count=c.execute("SELECT count(*) AS n FROM participant_recordings WHERE session_id=%s AND status='prepared'", (s['id'],)).fetchone()['n']
                        if count==c.execute('SELECT required_recorder_count FROM recording_rooms WHERE id=%s',(p['room_id'],)).fetchone()['required_recorder_count']:
                            c.execute("UPDATE recording_sessions SET status='countdown',starts_at=%s WHERE id=%s", (time.time()*1000+countdown_seconds*1000,s['id']))
                            start_countdown=True
                    elif kind == 'started' and s['status'] in ('recording','finalizing','interrupted') :
                        c.execute('UPDATE recording_sessions SET started_at=COALESCE(started_at,%s) WHERE id=%s',(time.time()*1000,s['id']))
                        values=[float(m['client_ms']),float(m['performance_ms'])]
                        if not all(math.isfinite(x) and x>=0 for x in values):
                            raise ValueError('時間無效')
                        c.execute("UPDATE participant_recordings SET status=CASE WHEN interrupted THEN 'interrupted' ELSE %s END,error=CASE WHEN interrupted THEN error ELSE NULL END,actual_started_at=%s,start_perf_ms=%s,server_started_at=now() WHERE session_id=%s AND participant_id=%s AND actual_started_at IS NULL AND mime_type IS NOT NULL", ('recording' if s['status']=='recording' else 'uploading',*values,s['id'],p['id']))
                    elif kind == 'error':
                        error=str(m.get('message','裝置錯誤'))[:300]
                        if m.get('permission')=='denied':
                            c.execute("UPDATE room_participants SET microphone_permission='denied' WHERE id=%s",(p['id'],))
                        c.execute('UPDATE room_participants SET ready=false,mic=false,error=%s WHERE id=%s', (error,p['id']))
                        if s['status'] in ('recording','finalizing'):
                            c.execute("UPDATE participant_recordings SET interrupted=true,status='interrupted',error=%s WHERE session_id=%s AND participant_id=%s AND status NOT IN ('stored','interrupted')", (error,s['id'],p['id']))
                    elif kind == 'clock' and p['source_label']:
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
    from backend.analysis import register_analysis
    register_analysis(app)

    return app


app = create_app()
