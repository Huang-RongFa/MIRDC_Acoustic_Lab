import os
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from backend.app import create_app
from backend.db import Database
from backend.schema import check_schema


def test_departure_migration_repeated_preserves_data():
    db = Database(os.environ['TEST_DATABASE_URL'])
    with db.transaction() as c:
        before = c.execute('SELECT id,leaving,revoked,source_label FROM room_participants ORDER BY id').fetchall()
    sql = Path('backend/migrations/006_participant_state_compat.sql').read_text()
    for _ in range(2):
        with db.transaction() as c:
            c.execute(sql)
            check_schema(c)
    with db.transaction() as c:
        assert c.execute('SELECT id,leaving,revoked,source_label FROM room_participants ORDER BY id').fetchall() == before


def test_preflight_catches_missing_column_without_updates():
    # Transactional DDL is rolled back; use only the isolated test database.
    db = Database(os.environ['TEST_DATABASE_URL'])
    with db.transaction() as c:
        before=c.execute('SELECT count(*) AS n FROM room_participants').fetchone()
        with pytest.raises(RuntimeError,match='room_participants.leaving'):
            with c.transaction():
                c.execute('ALTER TABLE room_participants RENAME COLUMN leaving TO test_old_leaving')
                check_schema(c)
        check_schema(c)
        assert c.execute('SELECT count(*) AS n FROM room_participants').fetchone()==before


def test_health_and_repeated_startup():
    for _ in range(2):
        with TestClient(create_app(os.environ['TEST_DATABASE_URL']),client=('127.0.0.1',50000)) as client:
            assert client.get('/api/health').json()=={'status':'ok','service':'cnc-acoustic-lab'}


def test_departure_migration_repairs_missing_flags():
    db=Database(os.environ['TEST_DATABASE_URL'])
    sql=Path('backend/migrations/006_participant_state_compat.sql').read_text().replace('BEGIN;','',1).removesuffix('COMMIT;\n')
    class RollbackFixture(Exception):
        pass
    with pytest.raises(RollbackFixture):
        with db.transaction() as c:
            count=c.execute('SELECT count(*) AS n FROM room_participants').fetchone()
            c.execute('ALTER TABLE room_participants RENAME COLUMN leaving TO fixture_leaving')
            c.execute('ALTER TABLE room_participants RENAME COLUMN revoked TO fixture_revoked')
            for _ in range(2):
                c.execute(sql)
                check_schema(c)
            assert c.execute('SELECT count(*) AS n FROM room_participants').fetchone()==count
            assert c.execute('SELECT count(*) AS n FROM room_participants WHERE leaving OR revoked').fetchone()['n']==0
            raise RollbackFixture()
