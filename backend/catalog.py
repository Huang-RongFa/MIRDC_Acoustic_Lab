from uuid import UUID, uuid4
from fastapi import Header, HTTPException
from psycopg.types.json import Jsonb
from backend.models import CatalogItem


def register_catalog(app):
    db=app.state.db
    authorize=app.state.authorize

    @app.get('/api/rooms/{code}/catalog')
    def catalog(code:str,authorization:str|None=Header(None)):
        with db.transaction() as c:
            p=authorize(c,code,authorization)
            items=c.execute('SELECT id,kind,name,values FROM catalog_items WHERE room_id=%s ORDER BY kind,name',(p['room_id'],)).fetchall()
            shared=c.execute("SELECT preset_id AS id,'presets' AS kind,preset_name AS name,extra_params->'capture_conditions' AS values FROM public.machining_presets WHERE is_active AND extra_params ? 'capture_conditions' ORDER BY preset_name").fetchall()
            names={item['name'] for item in shared}
            return {'items':[item for item in items if item['kind']!='presets' or item['name'] not in names]+shared}

    @app.put('/api/rooms/{code}/catalog')
    def save(code:str,body:CatalogItem,authorization:str|None=Header(None)):
        with db.transaction() as c:
            p=authorize(c,code,authorization,host=True)
            if body.kind=='presets':
                values=body.values.model_dump(mode='json')
                if body.values.machine_id and not c.execute('SELECT 1 FROM public.machines WHERE machine_id=%s AND is_active',(body.values.machine_id,)).fetchone():
                    raise HTTPException(422,'請選擇有效機台')
                saved=c.execute('''INSERT INTO public.machining_presets(preset_name,machine_id,process_type,extra_params)
                    VALUES(%s,%s,'other',%s) ON CONFLICT(preset_name) DO UPDATE SET
                    machine_id=excluded.machine_id,extra_params=public.machining_presets.extra_params || excluded.extra_params,updated_at=now(),is_active=true
                    WHERE public.machining_presets.extra_params ? 'capture_conditions' RETURNING preset_id''',
                    (body.name,body.values.machine_id,Jsonb({'capture_conditions':values}))).fetchone()
                if not saved:
                    raise HTTPException(409,'此名稱已由其他加工範本使用，請更換名稱')
                return {'ok':True}
            if body.kind=='machines':
                if not body.values.machine_code:
                    raise HTTPException(422,'請輸入機台編號')
                c.execute('''INSERT INTO public.machines(machine_code,machine_name,machine_type,model)
                    VALUES(%s,%s,%s,%s) ON CONFLICT(machine_code) DO UPDATE SET
                    machine_name=excluded.machine_name,machine_type=excluded.machine_type,model=excluded.model''',
                    (body.values.machine_code,body.name,body.values.machine_type,body.values.machine_model))
            c.execute('INSERT INTO catalog_items(id,room_id,kind,name,values) VALUES(%s,%s,%s,%s,%s) ON CONFLICT(room_id,kind,name) DO UPDATE SET values=excluded.values',(str(uuid4()),p['room_id'],body.kind,body.name,Jsonb(body.values.model_dump(mode="json"))))
        return {'ok':True}

    @app.delete('/api/rooms/{code}/catalog/{item_id}')
    def delete_item(code:str,item_id:UUID,authorization:str|None=Header(None)):
        with db.transaction() as c:
            actor=authorize(c,code,authorization,host=True)
            if not c.execute('DELETE FROM catalog_items WHERE room_id=%s AND id=%s RETURNING id',(actor['room_id'],item_id)).fetchone():
                raise HTTPException(404,'找不到設定')
        return {'ok':True}

    @app.get('/api/rooms/{code}/analysis')
    def analysis(code:str,authorization:str|None=Header(None)):
        with db.transaction() as c:
            p=authorize(c,code,authorization)
            return {'results':c.execute('SELECT a.id,a.result,a.created_at FROM analysis_results a JOIN recording_sessions s ON s.id=a.session_id WHERE s.room_id=%s ORDER BY a.created_at DESC',(p['room_id'],)).fetchall()}
