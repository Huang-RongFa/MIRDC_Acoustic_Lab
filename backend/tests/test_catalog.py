import os
from uuid import uuid4
from fastapi.testclient import TestClient
from backend.app import create_app
from backend.tests.test_api import CONDITIONS


def test_settings_are_persisted_and_analysis_is_not_fabricated():
    with TestClient(create_app(os.environ['TEST_DATABASE_URL']),client=('127.0.0.1',50000)) as c:
        host=c.post('/api/rooms',json={'name':'A','record_as_host':True}).json()
        base='/api/rooms/'+host['room_code']
        headers={'Authorization':'Bearer '+host['token']}
        body={'kind':'presets','name':'AL6061-'+str(uuid4()),'values':CONDITIONS}
        assert c.put(base+'/catalog',headers=headers,json=body).status_code==200
        body['values']={**CONDITIONS,'spindle_rpm':7000}
        assert c.put(base+'/catalog',headers=headers,json=body).status_code==200
        items=[item for item in c.get(base+'/catalog',headers=headers).json()['items'] if item['name']==body['name']]
        assert len(items)==1
        assert items[0]['values']['spindle_rpm']==7000
        assert c.get(base+'/analysis',headers=headers).json()=={'results':[]}


def test_machine_and_conditions_available_in_new_room():
    with TestClient(create_app(os.environ['TEST_DATABASE_URL']),client=('127.0.0.1',50000)) as c:
        first=c.post('/api/rooms',json={'name':'主控'}).json()
        headers={'Authorization':'Bearer '+first['token']}
        base='/api/rooms/'+first['room_code']
        code='machine-'+str(uuid4())
        machine={'machine_code':code,'machine_name':'測試機台','machine_type':'CNC','machine_model':'VMC'}
        assert c.put(base+'/catalog',headers=headers,json={'kind':'machines','name':'測試機台','values':machine}).status_code==200
        saved=next(m for m in c.get('/api/machines',headers=headers).json()['items'] if m['machine_code']==code)
        assert saved['machine_model']=='VMC'
        name='preset-'+str(uuid4())
        values={**saved,'material':'AL6061','material_spec':'T6','spindle_rpm':7000}
        assert c.put(base+'/catalog',headers=headers,json={'kind':'presets','name':name,'values':values}).status_code==200
        assert c.post(base+'/close',headers=headers).status_code==200
        second=c.post('/api/rooms',json={'name':'新主控'}).json()
        headers={'Authorization':'Bearer '+second['token']}
        base='/api/rooms/'+second['room_code']
        assert any(m['machine_code']==code for m in c.get('/api/machines',headers=headers).json()['items'])
        preset=next(item for item in c.get(base+'/catalog',headers=headers).json()['items'] if item['name']==name)
        assert preset['values']['machine_id']==saved['machine_id']
        assert preset['values']['material_spec']=='T6'
        assert preset['values']['spindle_rpm']==7000
        assert c.put(base+'/conditions',headers=headers,json=preset['values']).status_code==200
