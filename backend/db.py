from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row


class Database:
    def __init__(self, url):
        self.url = url

    @contextmanager
    def transaction(self):
        with psycopg.connect(self.url, row_factory=dict_row, connect_timeout=5) as connection:
            connection.execute('SET search_path TO mobile_capture, public')
            yield connection

    @contextmanager
    def control_lease(self):
        with psycopg.connect(self.url, autocommit=True, connect_timeout=5) as connection:
            if not connection.execute('SELECT pg_try_advisory_lock(73124491)').fetchone()[0]:
                raise RuntimeError('此資料庫已有錄音控制服務；請使用單一 worker')
            try:
                yield
            finally:
                connection.execute('SELECT pg_advisory_unlock(73124491)')
