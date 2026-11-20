"""地端分析 worker 的資料庫整合測試（需要一個可建立資料庫的 PostgreSQL 測試帳號）。

每個測試都建一個全新的資料庫，套用 backend/migrations 001–004 與 deploy/analysis_worker_role.sql，
並用最小權限帳號 analysis_worker 跑 worker，測完刪除。不碰任何既有資料庫。
  $env:WORKER_TEST_ADMIN_URL = 'postgresql://postgres@127.0.0.1:55433/postgres'
  python -X utf8 analysis/tests/test_worker.py
"""
import hashlib
import os
import subprocess
import sys
import tempfile
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

import psycopg
import soundfile as sf
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

import worker  # noqa: E402

ADMIN = os.environ.get("WORKER_TEST_ADMIN_URL")
MIGRATIONS = sorted((ROOT / "backend" / "migrations").glob("00[1-4]_*.sql"))
ROLE_SQL = ROOT / "deploy" / "analysis_worker_role.sql"
MIME = "audio/webm;codecs=opus"


def url_for(db, user=None):
    d = conninfo_to_dict(ADMIN)
    d["dbname"] = db
    if user:
        d["user"] = user
    return make_conninfo(**d)


@contextmanager
def fresh_db():
    name = "worker_test_" + uuid.uuid4().hex[:10]
    with psycopg.connect(ADMIN, autocommit=True) as a:
        a.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    try:
        with psycopg.connect(url_for(name), autocommit=True) as c:
            for f in MIGRATIONS + [ROLE_SQL]:
                c.execute(f.read_text(encoding="utf-8"))
        yield url_for(name), url_for(name, "analysis_worker")
    finally:
        with psycopg.connect(ADMIN, autocommit=True) as a:
            a.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name)))


def seed_session(admin_url, tracks, corrupt=None, complete=True):
    """tracks: {"A": webm bytes, ...}。corrupt=(label, chunk_index) 時該段存入錯誤的 checksum。"""
    room, session = uuid.uuid4(), uuid.uuid4()
    with psycopg.connect(admin_url) as c:
        c.execute("SET search_path TO mobile_capture")
        c.execute("INSERT INTO recording_rooms(id,code) VALUES(%s,%s)", (room, uuid.uuid4().hex[:6].upper()))
        c.execute("INSERT INTO recording_sessions(id,room_id,status) VALUES(%s,%s,'finalizing')", (session, room))
        for label, data in tracks.items():
            pid = uuid.uuid4()
            c.execute("INSERT INTO room_participants(id,room_id,source_label,name,token_hash,is_host) VALUES(%s,%s,%s,%s,%s,%s)",
                      (pid, room, label, label, uuid.uuid4().hex, label == "A"))
            chunks = [data[i:i + 32768] for i in range(0, len(data), 32768)]
            c.execute("INSERT INTO participant_recordings(session_id,participant_id,room_id,status,mime_type,expected_chunks,actual_started_at) "
                      "VALUES(%s,%s,%s,'stored',%s,%s,0)", (session, pid, room, MIME, len(chunks)))
            for i, ch in enumerate(chunks):
                digest = hashlib.sha256(ch).hexdigest()
                if corrupt == (label, i):
                    digest = hashlib.sha256(b"tampered" + ch).hexdigest()
                c.execute("INSERT INTO audio_chunks(session_id,participant_id,chunk_index,mime_type,created_at,checksum,audio_data) "
                          "VALUES(%s,%s,%s,%s,%s,%s,%s)", (session, pid, i, MIME, i * 1000.0, digest, ch))
            c.execute("INSERT INTO audio_assets(session_id,participant_id,mime_type,chunk_count,byte_count,checksum) VALUES(%s,%s,%s,%s,%s,%s)",
                      (session, pid, MIME, len(chunks), len(data), hashlib.sha256(data).hexdigest()))
        if complete:
            c.execute("UPDATE recording_sessions SET status='completed' WHERE id=%s", (session,))
    return session


def jobs(admin_url):
    with psycopg.connect(admin_url) as c:
        return c.execute("SELECT status,attempts,error,worker_id,finished_at FROM mobile_capture.analysis_jobs ORDER BY created_at").fetchall()


_WEBM = {}


def synthetic_webm():
    """合成三麥克風（已知偏移、C 有 25 ppm 漂移、含嗶聲）→ Opus webm，和手機上傳的格式相同。"""
    if _WEBM:
        return _WEBM
    import test_synthetic as ts
    rec = ts.recordings(with_chirp=True)
    with tempfile.TemporaryDirectory() as d:
        for k, y in rec.items():
            wav, webm = Path(d) / f"{k}.wav", Path(d) / f"{k}.webm"
            sf.write(wav, y.astype("float32"), ts.SR, subtype="FLOAT")
            subprocess.run([worker.ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y", "-i", str(wav),
                            "-c:a", "libopus", "-b:a", "128k", str(webm)], check=True, timeout=120)
            _WEBM[k] = webm.read_bytes()
    return _WEBM


# ---------- 測試 ----------

def test_completion_trigger_enqueues_exactly_once():
    with fresh_db() as (admin, _):
        s = seed_session(admin, {"A": b"x" * 10, "B": b"y" * 10}, complete=False)
        assert jobs(admin) == [], "未完成的錄音不應排入分析"
        with psycopg.connect(admin) as c:
            c.execute("UPDATE mobile_capture.recording_sessions SET status='completed' WHERE id=%s", (s,))
            c.execute("UPDATE mobile_capture.recording_sessions SET status='completed' WHERE id=%s", (s,))
        j = jobs(admin)
        assert len(j) == 1 and j[0][0] == "queued" and j[0][1] == 0, j


def test_session_completion_by_role_without_job_grants_still_enqueues():
    """後端帳號沒有 analysis_jobs 權限時，完成錄音不能因 trigger 失敗。"""
    with fresh_db() as (admin, _):
        s = seed_session(admin, {"A": b"x", "B": b"y"}, complete=False)
        with psycopg.connect(admin, autocommit=True) as c:
            c.execute("DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='backend_like') "
                      "THEN CREATE ROLE backend_like LOGIN; END IF; END $$")
            c.execute("GRANT USAGE ON SCHEMA mobile_capture TO backend_like")
            c.execute("GRANT SELECT, UPDATE ON mobile_capture.recording_sessions TO backend_like")
        with psycopg.connect(url_for(conninfo_to_dict(admin)["dbname"], "backend_like")) as c:
            c.execute("UPDATE mobile_capture.recording_sessions SET status='completed' WHERE id=%s", (s,))
        j = jobs(admin)
        assert len(j) == 1 and j[0][0] == "queued", j


def test_worker_role_runs_full_pipeline_and_writes_verified_alignment():
    import test_synthetic as ts
    tracks = synthetic_webm()
    with fresh_db() as (admin, role) , tempfile.TemporaryDirectory() as work:
        seed_session(admin, tracks)
        assert worker.run_once(role, "test-worker", work, 60, 900, "testcommit") is True
        j = jobs(admin)
        assert j[0][0] == "completed" and j[0][1] == 1 and j[0][2] is None and j[0][4] is not None, j
        with psycopg.connect(admin) as c:
            result = c.execute("SELECT result FROM mobile_capture.analysis_results").fetchone()[0]
            align = c.execute("SELECT status,offsets FROM mobile_capture.audio_alignment_runs").fetchone()
        assert result["alignment"]["verified"] is True, result["alignment"]
        assert align[0] == "verified", align
        assert result["pipeline_version"] == worker.PIPELINE_VERSION and result["code_commit"] == "testcommit"
        b, cc = result["summary"]["sync"]["B_vs_A"], result["summary"]["sync"]["C_vs_A"]
        # 三軌經同一個 Opus 編碼器，編碼延遲相同，相對偏移應保留
        assert abs(b["fine_offset_samples"] - ts.expected_offset("B")) < 2, b["fine_offset_samples"]
        assert abs(cc["drift_ppm"] - 25) < 3, cc["drift_ppm"]
        # 地端輸出留在 work dir，不進資料庫
        assert list(Path(work).glob("*/*/attempt-1/out/fig1_sync.png")), "地端應保留圖檔（每次嘗試各自資料夾）"
        assert "worker_id" not in result and "local_output" not in result, "結果 JSON 會回給手機，不可含地端主機資訊"
        assert result["alignment"]["channels"] == ["A", "B", "C"]
        # 最小權限：不能新增工作、不能刪音段
        with psycopg.connect(role) as c:
            for stmt in ("INSERT INTO mobile_capture.analysis_jobs(session_id) SELECT id FROM mobile_capture.recording_sessions",
                         "DELETE FROM mobile_capture.audio_chunks",
                         "UPDATE mobile_capture.analysis_jobs SET session_id=session_id",
                         "SELECT token_hash FROM mobile_capture.room_participants",
                         "SELECT conditions FROM mobile_capture.recording_sessions"):
                try:
                    with c.transaction():
                        c.execute(stmt)
                except psycopg.errors.InsufficientPrivilege:
                    continue
                raise AssertionError(f"worker 帳號不應能執行：{stmt}")


def test_corrupt_chunk_is_retried_then_failed_without_results():
    with fresh_db() as (admin, role), tempfile.TemporaryDirectory() as work:
        seed_session(admin, {"A": b"a" * 70000, "B": b"b" * 70000}, corrupt=("B", 1))
        states = []
        for _ in range(4):
            worker.run_once(role, "test-worker", work, 60, 60, None)
            states.append(jobs(admin)[0][:3])
        assert [s[0] for s in states] == ["queued", "queued", "failed", "failed"], states
        assert states[-1][1] == 3 and "B" in states[-1][2] and "SHA256" in states[-1][2], states
        assert worker.run_once(role, "test-worker", work, 60, 60, None) is None, "失敗的工作不應再被認領"
        with psycopg.connect(admin) as c:
            assert c.execute("SELECT count(*) FROM mobile_capture.analysis_results").fetchone()[0] == 0


def test_two_workers_cannot_claim_the_same_job():
    with fresh_db() as (admin, role):
        seed_session(admin, {"A": b"a", "B": b"b"})
        with worker.connect(role) as c1, worker.connect(role) as c2:
            first = worker.claim(c1, "w1", 60, None)
            second = worker.claim(c2, "w2", 60, None)
        assert first is not None and second is None, (first, second)


def test_expired_lease_is_reclaimed_and_stale_worker_cannot_write():
    with fresh_db() as (admin, role):
        seed_session(admin, {"A": b"a", "B": b"b"})
        with worker.connect(role) as c:
            stale = worker.claim(c, "w1", 1, None)
        time.sleep(2.5)
        with worker.connect(role) as c:
            fresh = worker.claim(c, "w2", 60, None)
        assert fresh is not None and fresh["id"] == stale["id"] and fresh["attempts"] == 2
        assert worker.renew(role, stale["id"], "w1", stale["attempts"], 60) is False, "舊 worker 的租約不應能延長"
        with worker.connect(role) as c:
            wrote = worker.complete(c, stale, "w1", {"sync": {}})
        assert wrote is False
        with psycopg.connect(admin) as c:
            assert c.execute("SELECT count(*) FROM mobile_capture.analysis_results").fetchone()[0] == 0
            assert c.execute("SELECT worker_id FROM mobile_capture.analysis_jobs").fetchone()[0] == "w2"


def test_expired_lease_at_attempt_limit_becomes_failed():
    with fresh_db() as (admin, role):
        seed_session(admin, {"A": b"a", "B": b"b"})
        with psycopg.connect(admin) as c:
            c.execute("UPDATE mobile_capture.analysis_jobs SET status='running',attempts=3,worker_id='gone',"
                      "lease_expires_at=now()-interval '1 minute'")
        with worker.connect(role) as c:
            assert worker.claim(c, "w2", 60, None) is None
        j = jobs(admin)[0]
        assert j[0] == "failed" and j[4] is not None and "重試上限" in j[2], j


def test_rerunning_role_script_removes_previous_column_grants():
    """既有帳號曾被授予敏感欄位時，重跑 deploy/analysis_worker_role.sql 要把它收回。"""
    with fresh_db() as (admin, role):
        with psycopg.connect(admin, autocommit=True) as c:
            c.execute("GRANT SELECT (token_hash, name) ON mobile_capture.room_participants TO analysis_worker")
            c.execute("GRANT SELECT ON mobile_capture.recording_sessions TO analysis_worker")
            c.execute(ROLE_SQL.read_text(encoding="utf-8"))
            q = "SELECT has_column_privilege('analysis_worker','mobile_capture.room_participants',%s,'SELECT')"
            assert c.execute(q, ("token_hash",)).fetchone()[0] is False
            assert c.execute(q, ("name",)).fetchone()[0] is False
            assert c.execute(q, ("source_label",)).fetchone()[0] is True
            assert c.execute("SELECT has_table_privilege('analysis_worker','mobile_capture.recording_sessions','SELECT')").fetchone()[0] is False


def test_reused_worker_id_cannot_touch_a_newer_attempt():
    """同一個 worker_id 重新認領後，舊嘗試的延長、失敗、完成都必須寫不進去（避免工作卡在 queued）。"""
    with fresh_db() as (admin, role):
        seed_session(admin, {"A": b"a", "B": b"b"})
        with worker.connect(role) as c:
            first = worker.claim(c, "same", 1, None)
        time.sleep(2.5)
        with worker.connect(role) as c:
            second = worker.claim(c, "same", 60, None)
        assert second["attempts"] == 2
        with psycopg.connect(admin) as c:
            c.execute("UPDATE mobile_capture.analysis_jobs SET max_attempts=2")
        assert worker.renew(role, first["id"], "same", first["attempts"], 60) is False
        with worker.connect(role) as c:
            worker.fail(c, first, "same", "stale failure")
        j = jobs(admin)[0]
        assert j[0] == "running" and j[1] == 2 and j[2] is None, f"舊嘗試不應改到新嘗試：{j}"
        with worker.connect(role) as c:
            assert worker.complete(c, first, "same", {"channels": ["A", "B"], "sync": {}}) is False
        with worker.connect(role) as c:
            worker.fail(c, second, "same", "real failure")
        j = jobs(admin)[0]
        assert j[0] == "failed" and j[2] == "real failure", j


def test_lost_lease_kills_the_running_analysis():
    import threading
    with tempfile.TemporaryDirectory() as d:
        slow = Path(d) / "slow.py"
        slow.write_text("import time\ntime.sleep(60)\n", encoding="utf-8")
        cancel = threading.Event()
        threading.Timer(1.0, cancel.set).start()
        t0 = time.time()
        try:
            worker.analyse({"A": Path(d) / "A.wav", "B": Path(d) / "B.wav"}, Path(d) / "out", "", 120, cancel, analyzer=slow)
        except worker.LeaseLost:
            pass
        else:
            raise AssertionError("失去租約時應中止分析")
        assert time.time() - t0 < 10, "子程序應立即被終止"


def test_public_error_hides_local_paths():
    msg = worker.public_error("Traceback\n" r"FileNotFoundError: No such file: 'C:\data\cnc\A.wav' or /srv/x")
    assert "data" not in msg and "srv" not in msg and "FileNotFoundError" in msg, msg
    spaced = worker.public_error(r"OSError: cannot open 'C:\Private Customer\secret.wav'")
    assert "Customer" not in spaced and "secret" not in spaced and "OSError" in spaced, spaced
    assert worker.public_error("RuntimeError: 精對齊失敗：峰值清楚的窗只有 0 個").endswith("峰值清楚的窗只有 0 個")
    assert worker.public_error("killed") == "分析程式失敗（詳見地端 log）"


def test_verdict_rejects_unmeasurable_or_large_residuals():
    good = {"fine_offset_samples": 0.1, "drift_ppm": 0.3}
    ok = {"channels": ["A", "B"], "sync": {"B_vs_A": {"after_alignment": good}}}
    assert worker.alignment_verdict(ok)["verified"] is True
    bad = {"channels": ["A", "B", "C"],
           "sync": {"B_vs_A": {"after_alignment": {"fine_offset_samples": -71.9, "drift_ppm": -996.5}},
                    "C_vs_A": {"after_alignment": {"error": "精對齊失敗"}}}}
    v = worker.alignment_verdict(bad)
    assert v["verified"] is False and set(v["failed_pairs"]) == {"B_vs_A", "C_vs_A"}, v
    # 三軌但少了 C 的配對、欄位缺漏或非數字，都不能算通過，也不能丟例外
    missing_pair = worker.alignment_verdict({"channels": ["A", "B", "C"], "sync": {"B_vs_A": {"after_alignment": good}}})
    assert missing_pair["failed_pairs"] == {"C_vs_A": "對齊後無法重新量測"}, missing_pair
    for after in ({}, {"fine_offset_samples": 0.1}, {"fine_offset_samples": float("nan"), "drift_ppm": 0},
                  {"fine_offset_samples": "0", "drift_ppm": 0}):
        v = worker.alignment_verdict({"channels": ["A", "B"], "sync": {"B_vs_A": {"after_alignment": after}}})
        assert v["verified"] is False and "B_vs_A" in v["failed_pairs"], (after, v)
    assert worker.alignment_verdict({"sync": {}})["verified"] is False


if __name__ == "__main__":
    if not ADMIN:
        print("請設定 WORKER_TEST_ADMIN_URL（可建立資料庫的測試帳號）")
        sys.exit(2)
    tests = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in tests:
        t0 = time.time()
        try:
            fn()
            print(f"PASS {fn.__name__} ({time.time() - t0:.1f}s)")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL {fn.__name__}: {type(e).__name__}: {e}")
    print(f"{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
