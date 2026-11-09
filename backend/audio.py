import hashlib
import math
from uuid import UUID

from fastapi import Header, HTTPException, Request
from fastapi.responses import StreamingResponse

from backend.models import Finish


def register_audio(app):
    db = app.state.db
    authorize = app.state.authorize
    publish = app.state.publish

    def recording(c, code, pid, authorization, owner=True):
        p = authorize(c, code, authorization)
        if owner and str(p['id']) != str(pid):
            raise HTTPException(403, '只能上傳自己的聲源')
        r = c.execute('SELECT pr.*,s.status AS session_status FROM participant_recordings pr JOIN recording_sessions s ON s.id=pr.session_id WHERE pr.room_id=%s AND pr.participant_id=%s FOR UPDATE OF s,pr', (p['room_id'],pid)).fetchone()
        if not r:
            raise HTTPException(404, '找不到此房間的錄音')
        return p,r

    @app.put('/api/rooms/{code}/recordings/{pid}/chunks/{index}')
    async def chunk(code: str, pid: UUID, index: int, request: Request,
                    authorization: str | None = Header(None), x_checksum: str = Header(),
                    x_created_at: float = Header(), content_type: str = Header()):
        if index < 0 or index >= 10000000 or not math.isfinite(x_created_at) or x_created_at<0:
            raise HTTPException(422, '分段索引或時間無效')
        with db.transaction() as c:
            recording(c,code,pid,authorization)
        data=bytearray()
        async for part in request.stream():
            data.extend(part)
            if len(data)>8388608:
                raise HTTPException(413,'單一分段不可超過 8 MiB')
        if not data or hashlib.sha256(data).hexdigest()!=x_checksum:
            raise HTTPException(422,'音訊 SHA256 校驗失敗')
        with db.transaction() as c:
            p,r=recording(c,code,pid,authorization)
            if r['session_status'] not in ('recording','finalizing','completed','interrupted') or r['actual_started_at'] is None:
                raise HTTPException(409,'尚未回報實際開始錄音')
            if content_type != r['mime_type']:
                raise HTTPException(422,'音訊格式與本機準備資料不符')
            previous=c.execute('SELECT checksum,created_at,mime_type FROM audio_chunks WHERE session_id=%s AND participant_id=%s AND chunk_index=%s', (r['session_id'],pid,index)).fetchone()
            if previous:
                if previous['checksum']!=x_checksum or previous['created_at']!=x_created_at or previous['mime_type']!=content_type:
                    raise HTTPException(409,'相同分段索引的內容或中繼資料衝突')
                return {'ok':True,'duplicate':True}
            if r['status']=='stored' or (r['expected_chunks'] is not None and index>=r['expected_chunks']):
                raise HTTPException(409,'超出已宣告的音訊分段範圍')
            c.execute('INSERT INTO audio_chunks(session_id,participant_id,chunk_index,mime_type,created_at,checksum,audio_data) VALUES(%s,%s,%s,%s,%s,%s,%s)', (r['session_id'],pid,index,content_type,x_created_at,x_checksum,bytes(data)))
        return {'ok':True,'duplicate':False}

    @app.get('/api/rooms/{code}/recordings/{pid}/chunks')
    def inventory(code: str,pid: UUID,authorization: str | None=Header(None)):
        with db.transaction() as c:
            _,r=recording(c,code,pid,authorization)
            rows=c.execute('SELECT chunk_index,checksum FROM audio_chunks WHERE session_id=%s AND participant_id=%s ORDER BY chunk_index',(r['session_id'],pid)).fetchall()
        return {'chunks':rows,'expected_chunks':r['expected_chunks']}

    @app.post('/api/rooms/{code}/recordings/{pid}/finish')
    async def finish(code: str,pid: UUID,body: Finish,authorization: str | None=Header(None)):
        missing=False
        with db.transaction() as c:
            p,r=recording(c,code,pid,authorization)
            if r['session_status'] not in ('finalizing','completed','interrupted'):
                raise HTTPException(409,'等待主控停止錄音')
            if r['actual_started_at'] is None:
                raise HTTPException(409,'缺少錄音開始確認')
            if r['expected_chunks'] is not None and r['expected_chunks'] != body.chunk_count:
                raise HTTPException(409,'分段總數與先前宣告不一致')
            if r['stopped_at'] is not None:
                if (body.interrupted and not r['interrupted']) or r['stopped_at'] != body.client_ms:
                    raise HTTPException(409,'已封存的完成宣告不可變更')
                return {'ok':True,'interrupted':r['interrupted']}
            count=c.execute('SELECT count(*) AS n,min(chunk_index) AS first,max(chunk_index) AS last FROM audio_chunks WHERE session_id=%s AND participant_id=%s', (r['session_id'],pid)).fetchone()
            missing=count['n']!=body.chunk_count or count['first']!=0 or count['last']!=body.chunk_count-1
            interrupted=r['interrupted'] or body.interrupted
            if missing:
                c.execute("UPDATE participant_recordings SET expected_chunks=%s,status='failed',error='分段不完整，等待補傳' WHERE session_id=%s AND participant_id=%s", (body.chunk_count,r['session_id'],pid))
            else:
                sha=hashlib.sha256()
                size=0
                with c.cursor(name='hash_chunks') as cursor:
                    cursor.execute('SELECT audio_data FROM audio_chunks WHERE session_id=%s AND participant_id=%s ORDER BY chunk_index',(r['session_id'],pid))
                    for row in cursor:
                        sha.update(row['audio_data'])
                        size+=len(row['audio_data'])
                c.execute('INSERT INTO audio_assets(session_id,participant_id,mime_type,chunk_count,byte_count,checksum) VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING', (r['session_id'],pid,r['mime_type'],body.chunk_count,size,sha.hexdigest()))
                c.execute('UPDATE participant_recordings SET expected_chunks=%s,stopped_at=%s,status=%s,interrupted=%s,error=%s,duration_ms=%s,server_stopped_at=now() WHERE session_id=%s AND participant_id=%s', (body.chunk_count,body.client_ms,'interrupted' if interrupted else 'stored',interrupted,'錄音中斷；已保存可用分段' if interrupted else None,body.duration_ms,r['session_id'],pid))
                complete=c.execute("SELECT count(*) AS n FROM participant_recordings WHERE session_id=%s AND status='stored' AND NOT interrupted", (r['session_id'],)).fetchone()['n']
                if complete==3:
                    c.execute("UPDATE recording_sessions SET status='completed' WHERE id=%s", (r['session_id'],))
                elif c.execute('SELECT count(*) AS n FROM audio_assets WHERE session_id=%s',(r['session_id'],)).fetchone()['n']==3:
                    c.execute("UPDATE recording_sessions SET status='interrupted' WHERE id=%s",(r['session_id'],))
        await publish(p['room_id'])
        if missing:
            raise HTTPException(409,'分段不完整；請補傳後重新完成')
        return {'ok':True,'interrupted':interrupted}

    @app.get('/api/rooms/{code}/recordings/{pid}/audio')
    def audio(code: str,pid: UUID,authorization: str | None=Header(None)):
        with db.transaction() as c:
            _,r=recording(c,code,pid,authorization,owner=False)
            asset=c.execute('SELECT * FROM audio_assets WHERE session_id=%s AND participant_id=%s',(r['session_id'],pid)).fetchone()
            if not asset:
                raise HTTPException(409,'音檔尚未封存')
        def stream():
            with db.transaction() as c, c.cursor(name='download_chunks') as cursor:
                cursor.execute('SELECT audio_data FROM audio_chunks WHERE session_id=%s AND participant_id=%s ORDER BY chunk_index',(r['session_id'],pid))
                for row in cursor:
                    yield bytes(row['audio_data'])
        extension='m4a' if 'mp4' in asset['mime_type'] else 'ogg' if 'ogg' in asset['mime_type'] else 'webm'
        return StreamingResponse(stream(),media_type=asset['mime_type'],headers={'Content-Disposition':f'attachment; filename="{r["session_id"]}_{pid}.{extension}"','Content-Length':str(asset['byte_count']),'X-Checksum':asset['checksum']})
