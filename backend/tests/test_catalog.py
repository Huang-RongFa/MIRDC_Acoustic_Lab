import os
from fastapi.testclient import TestClient
from backend.app import create_app
from backend.tests.test_api import CONDITIONS


def test_settings_are_persisted_and_analysis_is_not_fabricated():
    with TestClient(create_app(os.environ['TEST_DATABASE_URL'])) as c:
        host=c.post('/api/rooms',json={'name':'A'}).json()
        base='/api/rooms/'+host['room_code']
        headers={'Authorization':'Bearer '+host['token']}
        body={'kind':'presets','name':'AL6061','values':CONDITIONS}
        assert c.put(base+'/catalog',headers=headers,json=body).status_code==200
        body['values']={**CONDITIONS,'spindle_rpm':7000}
        assert c.put(base+'/catalog',headers=headers,json=body).status_code==200
        items=c.get(base+'/catalog',headers=headers).json()['items']
        assert len(items)==1
        assert items[0]['values']['spindle_rpm']==7000
        assert c.get(base+'/analysis',headers=headers).json()=={'results':[]}
