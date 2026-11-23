"""Generate a real, isolated API fixture for Playwright. Run only against a test DB."""
import json
import os
from pathlib import Path
from fastapi.testclient import TestClient
from backend.app import create_app
from backend.tests.test_analysis_api import seed, finish, wait_result


if __name__ == '__main__':
    app=create_app(os.environ['TEST_DATABASE_URL'])
    with TestClient(app,client=('127.0.0.1',50000)) as client:
        host,people=seed(client,app,[(48000,[1000]),(44100,[2000,4000]),(48000,[3000])])
        for person in people:
            assert finish(client,person).status_code==200
        base=f"/api/v1/sessions/{host['session_id']}/analysis"
        result=wait_result(client,base,{'Authorization':'Bearer '+host['token']})
        assert result['status']=='completed'
        # Create a second real take for the same room to exercise session switching.
        with app.state.db.transaction() as c:
            from uuid import uuid4
            other=str(uuid4())
            c.execute("INSERT INTO recording_sessions(id,room_id,status) SELECT %s,room_id,'waiting' FROM recording_sessions WHERE id=%s",(other,host['session_id']))
        Path('tmp/analysis-ui-fixture.json').write_text(json.dumps({'identity':host,'other_session':other}),encoding='utf-8')
    print('Prepared real four-track fixture in tmp/analysis-ui-fixture.json')
