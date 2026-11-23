"""Persistent single-worker analysis queue using the existing room authorization."""
import asyncio
import hashlib
import json
import logging
from tempfile import TemporaryFile
from uuid import UUID, uuid4, uuid5, NAMESPACE_URL

from fastapi import Header, HTTPException, Query
from fastapi.responses import Response
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field, model_validator

log = logging.getLogger(__name__)


class AnalysisRange(BaseModel):
    start_seconds: float = Field(default=0, ge=0, allow_inf_nan=False)
    end_seconds: float | None = Field(default=None, gt=0, allow_inf_nan=False)

    @model_validator(mode='after')
    def ordered(self):
        if self.end_seconds is not None and self.end_seconds <= self.start_seconds:
            raise ValueError('結束時間必須大於開始時間')
        return self


def enqueue(c, session_id, interval):
    session = c.execute('SELECT * FROM recording_sessions WHERE id=%s FOR UPDATE', (session_id,)).fetchone()
    if not session or session['status'] not in ('finalizing', 'completed', 'interrupted'):
        raise HTTPException(409, '錄音尚未完成')
    assets = c.execute('''SELECT pr.participant_id,pr.status,a.checksum FROM participant_recordings pr
        LEFT JOIN audio_assets a USING(session_id,participant_id) WHERE pr.session_id=%s ORDER BY pr.participant_id''', (session_id,)).fetchall()
    if not any(asset['checksum'] for asset in assets):
        raise HTTPException(409, '尚無完整封存音檔')
    fingerprint = hashlib.sha256(json.dumps([str(assets), interval.model_dump(), 'v1.4.1'], sort_keys=True).encode()).hexdigest()
    existing = c.execute('SELECT id,status FROM track_analysis_runs WHERE session_id=%s AND fingerprint=%s', (session_id, fingerprint)).fetchone()
    if existing:
        if existing['status'] == 'failed':
            c.execute("UPDATE track_analysis_runs SET status='queued',result='{}' WHERE id=%s", (existing['id'],))
        return existing['id']
    job = uuid4()
    c.execute('''INSERT INTO track_analysis_runs(id,session_id,fingerprint,start_seconds,end_seconds,status)
                 VALUES(%s,%s,%s,%s,%s,'queued')''', (job, session_id, fingerprint, interval.start_seconds, interval.end_seconds))
    return job


def process_job(db, job):
    from backend.analysis_signal import PARAMETERS, package_versions, decode, calculate, render, matrix_file
    sid, jid = job['session_id'], job['id']
    with db.transaction() as c:
        sources = c.execute('''SELECT pr.*,p.name,a.checksum,a.byte_count FROM participant_recordings pr
            JOIN room_participants p ON p.id=pr.participant_id LEFT JOIN audio_assets a USING(session_id,participant_id)
            WHERE pr.session_id=%s ORDER BY pr.source_position,pr.participant_id''', (sid,)).fetchall()
    tracks, errors, computed = [], [], {}
    for source in sources:
        device = str(source['participant_id'])
        name = f"{source['source_position']} · {source['name']}"
        if not source['checksum']:
            errors.append(dict(device_id=device, device_name=name, status='missing', error='音檔尚未完整封存'))
            continue
        try:
            with TemporaryFile() as raw:
                checksum, size = hashlib.sha256(), 0
                with db.transaction() as c, c.cursor(name='analysis_source') as cursor:
                    cursor.execute('SELECT audio_data FROM audio_chunks WHERE session_id=%s AND participant_id=%s ORDER BY chunk_index', (sid, device))
                    for row in cursor:
                        data = bytes(row['audio_data'])
                        raw.write(data)
                        checksum.update(data)
                        size += len(data)
                if size != source['byte_count'] or checksum.hexdigest() != source['checksum']:
                    raise ValueError('原始音檔完整性驗證失敗')
                raw.seek(0)
                samples, rate = decode(raw)
            for index, channel in enumerate(samples):
                tid = str(uuid5(NAMESPACE_URL, f'cnc:{sid}:{device}:{index}'))
                label = 'Mono' if len(samples) == 1 else ('Left', 'Right')[index]
                track = dict(track_id=tid, session_id=str(sid), device_id=device, device_name=name,
                             channel_index=index, channel_label=label, source_channel_count=len(samples),
                             requested_sample_rate=source['requested_sample_rate'], original_sample_rate=rate,
                             actual_sample_rate=rate, reported_sample_rate=source['sample_rate'], analysis_sample_rate=44100,
                             duration_seconds=len(channel)/rate, total_frames=len(channel),
                             audio_asset_id=f'{sid}/{device}', source_checksum=source['checksum'],
                             analysis_status='no_data', spectrogram_url=None, mfcc_url=None)
                tracks.append(track)
                try:
                    result = calculate(channel, rate, job['start_seconds'], job['end_seconds'])
                    if result is not None:
                        track['analysis_status'] = 'completed'
                        track['valid_range'] = result['valid_range']
                        computed[tid] = result
                    else:
                        track['error'] = '選取區間沒有足夠的有效樣本（至少 2048 samples）'
                except Exception:
                    log.exception('Track analysis failed: %s', tid)
                    track.update(analysis_status='failed', error='此聲道分析失敗')
        except Exception as exc:
            log.exception('Source decode failed: %s', device)
            errors.append(dict(device_id=device, device_name=name, status='failed', error=str(exc) if isinstance(exc, ValueError) else '音檔無法解碼'))
    mfcc_limits = [min((float(value['mfcc'].min()) for value in computed.values()), default=-1),
                   max((float(value['mfcc'].max()) for value in computed.values()), default=1)]
    if mfcc_limits[0] == mfcc_limits[1]:
        mfcc_limits[1] += 1
    time_range = [job['start_seconds'], job['end_seconds'] or max((track['duration_seconds'] for track in tracks), default=job['start_seconds']+1)]
    time_range[1] = max(time_range[1], time_range[0] + .01)
    with db.transaction() as c:
        for track in tracks:
            keys = ['track_id','session_id','device_id','device_name','channel_index','channel_label','source_channel_count',
                    'requested_sample_rate','original_sample_rate','actual_sample_rate','analysis_sample_rate','duration_seconds','total_frames','analysis_status']
            c.execute('INSERT INTO recording_tracks('+','.join(keys)+') VALUES('+','.join(['%s']*len(keys))+') ON CONFLICT(track_id) DO UPDATE SET analysis_status=excluded.analysis_status', tuple(track[key] for key in keys))
            tid = track['track_id']
            if tid not in computed:
                continue
            # Save each channel independently so a rendering failure does not hide siblings.
            try:
                with c.transaction():
                    for kind in ('spectrogram', 'mfcc', 'matrices'):
                        data = matrix_file(computed[tid]) if kind == 'matrices' else render(computed[tid], kind, [-120, 0] if kind == 'spectrogram' else mfcc_limits, time_range)
                        c.execute('INSERT INTO track_analysis_artifacts VALUES(%s,%s,%s,%s) ON CONFLICT(run_id,track_id,kind) DO UPDATE SET content=excluded.content', (jid, tid, kind, data))
                for kind in ('spectrogram', 'mfcc'):
                    track[kind+'_url'] = f'/api/v1/sessions/{sid}/analysis/{jid}/tracks/{tid}/{kind}.png'
            except Exception:
                log.exception('Rendering failed: %s', tid)
                track.update(analysis_status='failed', error='圖表產生失敗')
                c.execute("UPDATE recording_tracks SET analysis_status='failed' WHERE track_id=%s", (tid,))
        success = sum(track['analysis_status'] == 'completed' for track in tracks)
        status = 'completed' if success == len(tracks) and success and not errors else 'partial' if success else 'failed'
        result = dict(session_id=str(sid), run_id=str(jid), status=status, analysis_sample_rate=44100,
                      tracks=tracks, source_errors=errors, completed_device_count=sum(bool(s['checksum']) for s in sources),
                      analyzable_track_count=success, duration_seconds=max((t['duration_seconds'] for t in tracks), default=0),
                      time_range=time_range, mfcc_color_range=mfcc_limits, parameters=PARAMETERS, versions=package_versions())
        c.execute('UPDATE track_analysis_runs SET status=%s,result=%s WHERE id=%s', (status, Jsonb(result), jid))


def work_once(db):
    with db.transaction() as c:
        job = c.execute("SELECT * FROM track_analysis_runs WHERE status='queued' ORDER BY created_at LIMIT 1 FOR UPDATE SKIP LOCKED").fetchone()
        if not job:
            return False
        c.execute("UPDATE track_analysis_runs SET status='running' WHERE id=%s", (job['id'],))
    try:
        process_job(db, job)
    except Exception:
        log.exception('Analysis job failed: %s', job['id'])
        with db.transaction() as c:
            c.execute("UPDATE track_analysis_runs SET status='failed',result=%s WHERE id=%s", (Jsonb({'error':'分析失敗，請檢查後端分析套件與服務日誌','tracks':[]}), job['id']))
    return True


async def worker(db, stop):
    while not stop.is_set():
        try:
            await asyncio.to_thread(work_once, db)
        except Exception:
            log.exception('Analysis queue unavailable')
        try:
            await asyncio.wait_for(stop.wait(), timeout=1)
        except asyncio.TimeoutError:
            pass


def register_analysis(app):
    db = app.state.db

    def authorize_session(c, sid, authorization, host=False):
        session = c.execute('''SELECT s.*,r.code FROM recording_sessions s JOIN recording_rooms r ON r.id=s.room_id WHERE s.id=%s''', (sid,)).fetchone()
        if not session:
            raise HTTPException(404, '找不到錄音批次')
        app.state.authorize(c, session['code'], authorization, host=host)
        return session

    @app.get('/api/v1/sessions/{session_id}/analysis')
    def get_analysis(session_id: UUID, authorization: str | None = Header(None),
                     start_seconds: float = Query(0, ge=0, allow_inf_nan=False), end_seconds: float | None = Query(None, gt=0, allow_inf_nan=False)):
        if end_seconds is not None and end_seconds <= start_seconds:
            raise HTTPException(422, '結束時間必須大於開始時間')
        with db.transaction() as c:
            session = authorize_session(c, session_id, authorization)
            job = c.execute('''SELECT * FROM track_analysis_runs WHERE session_id=%s AND start_seconds=%s
                AND end_seconds IS NOT DISTINCT FROM %s ORDER BY created_at DESC LIMIT 1''', (session_id, start_seconds, end_seconds)).fetchone()
            return {**(job['result'] if job else {}), 'session_id':session_id, 'session_name':f"Session {str(session_id)[:8]}",
                    'created_at':session['created_at'], 'status':job['status'] if job else 'not_started',
                    'recording_status':session['status'], 'tracks':job['result'].get('tracks', []) if job else []}

    @app.post('/api/v1/sessions/{session_id}/analysis', status_code=202)
    def start_analysis(session_id: UUID, body: AnalysisRange, authorization: str | None = Header(None)):
        with db.transaction() as c:
            authorize_session(c, session_id, authorization, host=True)
            jid = enqueue(c, session_id, body)
        return {'run_id':jid}

    @app.get('/api/v1/sessions/{session_id}/analysis/{run_id}/tracks/{track_id}/{kind}.png')
    def image(session_id: UUID, run_id: UUID, track_id: UUID, kind: str, authorization: str | None = Header(None)):
        if kind not in ('spectrogram','mfcc'):
            raise HTTPException(404, '找不到圖表')
        with db.transaction() as c:
            authorize_session(c, session_id, authorization)
            asset = c.execute('''SELECT a.content FROM track_analysis_artifacts a JOIN track_analysis_runs r ON r.id=a.run_id
                WHERE r.session_id=%s AND a.run_id=%s AND a.track_id=%s AND a.kind=%s''', (session_id,run_id,track_id,kind)).fetchone()
            if not asset:
                raise HTTPException(404, '圖表尚未產生')
        return Response(bytes(asset['content']), media_type='image/png', headers={'Cache-Control':'private, no-store', 'Content-Disposition':f'inline; filename="{track_id}-{kind}.png"'})
