from uuid import uuid4
from fastapi import Header
from psycopg.types.json import Jsonb
from backend.models import CatalogItem


def register_catalog(app):
    db=app.state.db
    authorize=app.state.authorize

    @app.get('/api/rooms/{code}/catalog')
    def catalog(code:str,authorization:str|None=Header(None)):
        with db.transaction() as c:
            p=authorize(c,code,authorization)
            return {'items':c.execute('SELECT id,kind,name,values FROM catalog_items WHERE room_id=%s ORDER BY kind,name',(p['room_id'],)).fetchall()}

    @app.put('/api/rooms/{code}/catalog')
    def save(code:str,body:CatalogItem,authorization:str|None=Header(None)):
        with db.transaction() as c:
            p=authorize(c,code,authorization,host=True)
            c.execute('INSERT INTO catalog_items(id,room_id,kind,name,values) VALUES(%s,%s,%s,%s,%s) ON CONFLICT(room_id,kind,name) DO UPDATE SET values=excluded.values',(str(uuid4()),p['room_id'],body.kind,body.name,Jsonb(body.values.model_dump())))
        return {'ok':True}

    @app.get('/api/rooms/{code}/analysis')
    def analysis(code:str,authorization:str|None=Header(None)):
        with db.transaction() as c:
            p=authorize(c,code,authorization)
            return {'results':c.execute('SELECT a.id,a.result,a.created_at FROM analysis_results a JOIN recording_sessions s ON s.id=a.session_id WHERE s.room_id=%s ORDER BY a.created_at DESC',(p['room_id'],)).fetchall()}
