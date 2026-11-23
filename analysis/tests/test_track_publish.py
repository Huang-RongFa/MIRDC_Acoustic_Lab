"""外部分析 worker 的資料庫整合測試（對接規格 2026-11-17 第 11 節的驗收項目）。

需要一個可建立資料庫的 PostgreSQL 測試帳號；每個測試建一個全新的資料庫，測完刪除，不碰任何既有資料庫。
  $env:WORKER_TEST_ADMIN_URL = 'postgresql://postgres@127.0.0.1:55433/postgres'
  python -X utf8 analysis/tests/test_track_publish.py

資料庫結構用的是儲存庫裡的正式檔案：
  public V1.2 schema → backend/migrations 的 001–005（依檔名順序，含兩個 004）→ 最小權限帳號腳本。
  006_participant_state_compat.sql 是需要操作者核准的修補檔，不在一般順序裡，所以不套用。
建好之後用網站自己的啟動檢查 backend/schema.py 的 check_schema 確認結構符合。
整條流程都用最小權限帳號 track_analysis_writer 執行。這仍然是測試用的本機資料庫，不是網站實際的資料庫。
"""
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

import numpy as np
import psycopg
import soundfile as sf
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.types.json import Jsonb

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE.parent))

from track_analysis import publish as pub  # noqa: E402
from track_analysis import signal_contract as sc  # noqa: E402
from track_analysis import source as src  # noqa: E402
from track_analysis import worker  # noqa: E402

ADMIN = os.environ.get("WORKER_TEST_ADMIN_URL")
SCHEMA = [ROOT / "CNC_Acoustic_Lab_DB_v1_2" / "01_schema_complete.sql"] + [
    ROOT / "backend" / "migrations" / n for n in
    ("001_mobile_capture.sql", "002_room_lifecycle.sql", "003_recording_metadata.sql", "004_analysis_jobs.sql",
     "004_multi_recorder.sql", "005_track_analysis.sql")] + [
    ROOT / "deploy" / "track_analysis_writer_role.sql"]
PNG = b"\x89PNG\r\n\x1a\n"


def url_for(db, user=None):
    d = conninfo_to_dict(ADMIN)
    d["dbname"] = db
    if user:
        d["user"] = user
    return make_conninfo(**d)


@contextmanager
def fresh_db():
    name = "track_test_" + uuid.uuid4().hex[:10]
    with psycopg.connect(ADMIN, autocommit=True) as a:
        a.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    try:
        with psycopg.connect(url_for(name), autocommit=True) as c:
            for f in SCHEMA:
                c.execute(f.read_text(encoding="utf-8"))
        yield url_for(name), url_for(name, "track_analysis_writer")
    finally:
        with psycopg.connect(ADMIN, autocommit=True) as a:
            a.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name)))


def tone(freq, sec, sr, amp=0.3):
    return amp * np.sin(2 * np.pi * freq * np.arange(int(sec * sr)) / sr)


_ENC = {}


def encode(key, y, sr, kind):
    """把訊號編成手機會上傳的容器。kind：opus（webm，解碼後一律 48000）、aac（mp4）、wav。"""
    if key not in _ENC:
        with tempfile.TemporaryDirectory() as d:
            wav = Path(d) / "in.wav"
            sf.write(wav, np.asarray(y, dtype=np.float32), sr, subtype="FLOAT")
            if kind == "wav":
                out, extra, mime = Path(d) / "o.wav", ["-c:a", "pcm_s16le"], "audio/wav"
            elif kind == "opus":
                out, extra, mime = Path(d) / "o.webm", ["-c:a", "libopus", "-b:a", "128k"], "audio/webm;codecs=opus"
            else:
                out, extra, mime = Path(d) / "o.mp4", ["-c:a", "aac", "-b:a", "192k"], "audio/mp4"
            subprocess.run([src.ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y", "-i", str(wav), *extra, str(out)],
                           check=True, timeout=120)
            _ENC[key] = (out.read_bytes(), mime)
    return _ENC[key]


def dev_mono_opus():      # 回報 44100，但 Opus 解碼後是 48000：以實際解碼為準
    return {"name": "錄音者 A", "audio": encode("mono_opus", tone(700, 4.0, 48000), 48000, "opus"), "reported_sr": 44100, "reported_ch": 1}


def dev_stereo_aac():     # 左 440 Hz、右 1000 Hz：兩軌必須不同
    y = np.stack([tone(440, 4.0, 44100), tone(1000, 4.0, 44100)], axis=1)
    return {"name": "錄音者 B", "audio": encode("stereo_aac", y, 44100, "aac"), "reported_sr": 44100, "reported_ch": 2}


def dev_mono_wav(sec=4.0, key="mono_wav"):
    return {"name": "錄音者 C", "audio": encode(key, tone(2000, sec, 44100), 44100, "wav"), "reported_sr": 44100, "reported_ch": 1}


def seed(admin_url, devices, status="completed"):
    """devices 的 audio 可以是 None（尚未封存）。corrupt=True 時第 0 段存入錯誤的 checksum。回傳 (session_id, [participant_id])。"""
    room, session, pids = uuid.uuid4(), uuid.uuid4(), []
    with psycopg.connect(admin_url) as c:
        c.execute("SET search_path TO mobile_capture")
        c.execute("INSERT INTO recording_rooms(id,code) VALUES(%s,%s)", (room, uuid.uuid4().hex[:6].upper()))
        machine = c.execute("INSERT INTO public.machines(machine_code,machine_name) VALUES(%s,'測試機台') RETURNING machine_id",
                            ("M-" + uuid.uuid4().hex[:8],)).fetchone()[0]
        c.execute("INSERT INTO recording_sessions(id,room_id,status,conditions,machine_id) VALUES(%s,%s,'finalizing',%s,%s)",
                  (session, room, Jsonb({"spindle_rpm": 6000}), machine))
        for pos, d in enumerate(devices):
            pid = uuid.uuid4()
            pids.append(pid)
            c.execute("INSERT INTO room_participants(id,room_id,source_label,name,token_hash,is_host) VALUES(%s,%s,%s,%s,%s,%s)",
                      (pid, room, "ABC"[pos], d["name"], uuid.uuid4().hex, pos == 0))
            c.execute("INSERT INTO participant_recordings(session_id,participant_id,room_id,status,expected_chunks,actual_started_at,"
                      "source_position,sample_rate,channel_count,requested_sample_rate,requested_channel_count,interrupted) "
                      "VALUES(%s,%s,%s,'stored',%s,0,%s,%s,%s,%s,%s,%s)",
                      (session, pid, room, None, "ABC"[pos], d.get("reported_sr"), d.get("reported_ch"), 48000, d.get("reported_ch"),
                       bool(d.get("interrupted"))))
            if d.get("audio") is not None:
                add_asset(c, session, pid, d["audio"], corrupt=d.get("corrupt"))
        c.execute("UPDATE recording_sessions SET status=%s WHERE id=%s", (status, session))
    return session, pids


def add_asset(c, session, pid, audio, corrupt=False):
    data, mime = audio
    chunks = [data[i:i + 20000] for i in range(0, len(data), 20000)]
    for i, ch in enumerate(chunks):
        digest = hashlib.sha256(ch).hexdigest()
        if corrupt and i == 0:
            digest = hashlib.sha256(b"tampered" + ch).hexdigest()
        c.execute("INSERT INTO mobile_capture.audio_chunks(session_id,participant_id,chunk_index,mime_type,created_at,checksum,audio_data) "
                  "VALUES(%s,%s,%s,%s,%s,%s,%s)", (session, pid, i, mime, i * 1000.0, digest, ch))
    c.execute("INSERT INTO mobile_capture.audio_assets(session_id,participant_id,mime_type,chunk_count,byte_count,checksum) "
              "VALUES(%s,%s,%s,%s,%s,%s)", (session, pid, mime, len(chunks), len(data), hashlib.sha256(data).hexdigest()))


def q(url, text, params=()):
    with psycopg.connect(url, row_factory=psycopg.rows.dict_row) as c:
        return c.execute(text, params).fetchall()


def run(writer_url, session, **kw):
    with worker.connect(writer_url) as conn:
        return worker.analyse_session(conn, session, **kw)


def input_digest(admin_url):
    """原始錄音表與加工條件的內容摘要，用來確認分析前後完全沒變。"""
    out = {}
    for table, cols, order in (("audio_chunks", "session_id,participant_id,chunk_index,checksum,md5(audio_data)", "1,2,3"),
                               ("audio_assets", "session_id,participant_id,chunk_count,byte_count,checksum", "1,2"),
                               ("participant_recordings", "session_id,participant_id,status,sample_rate,channel_count,interrupted", "1,2"),
                               ("recording_sessions", "id,status,conditions::text", "1"),
                               ("room_participants", "id,name,token_hash", "1")):
        rows = q(admin_url, f"SELECT {cols} FROM mobile_capture.{table} ORDER BY {order}")
        out[table] = hashlib.sha256(json.dumps(rows, default=str, sort_keys=True).encode()).hexdigest()
    return out


def matrices(admin_url, run_id, track_id):
    row = q(admin_url, "SELECT content FROM mobile_capture.track_analysis_artifacts WHERE run_id=%s AND track_id=%s AND kind='matrices'",
            (run_id, track_id))[0]
    return np.load(io.BytesIO(bytes(row["content"])))


# ---------- 測試 ----------

def test_one_two_one_devices_give_four_plus_four_images():
    """規格 11：1/2/1 得到 4＋4 張；Left／Right 不同；混合 44100／48000 且回報 metadata 不符時以實際解碼為準。"""
    with fresh_db() as (admin, writer):
        session, pids = seed(admin, [dev_mono_opus(), dev_stereo_aac(), dev_mono_wav()])
        before = input_digest(admin)
        s = run(writer, session)
        assert s["status"] == "completed" and s["tracks_completed"] == 4 and s["source_errors"] == 0, s
        runs = q(admin, "SELECT id,status,fingerprint,start_seconds,end_seconds,result FROM mobile_capture.track_analysis_runs")
        assert len(runs) == 1 and runs[0]["status"] == "completed" and str(runs[0]["id"]) == s["run_id"]
        assert runs[0]["fingerprint"].startswith("ext:mirdc-onprem:") and runs[0]["start_seconds"] == 0 and runs[0]["end_seconds"] is None
        res = runs[0]["result"]
        assert res["status"] == "completed" and res["run_id"] == s["run_id"] and res["session_id"] == str(session)
        assert res["analysis_sample_rate"] == 44100 and res["analyzable_track_count"] == 4 and res["completed_device_count"] == 3
        assert res["source_errors"] == [] and res["parameters"]["fft_size"] == 2048 and res["parameters"]["hop_length"] == 441
        kinds = q(admin, "SELECT kind, count(*) AS n FROM mobile_capture.track_analysis_artifacts WHERE run_id=%s GROUP BY kind", (runs[0]["id"],))
        assert {k["kind"]: k["n"] for k in kinds} == {"spectrogram": 4, "mfcc": 4, "matrices": 4}, kinds
        tracks = q(admin, "SELECT * FROM mobile_capture.recording_tracks ORDER BY device_name, channel_index")
        assert [(t["device_name"], t["channel_index"], t["channel_label"], t["source_channel_count"]) for t in tracks] == [
            ("A · 錄音者 A", 0, "Mono", 1), ("B · 錄音者 B", 0, "Left", 2), ("B · 錄音者 B", 1, "Right", 2),
            ("C · 錄音者 C", 0, "Mono", 1)], tracks                    # 顯示名稱和網站內建分析同一個格式
        for t in tracks:                                        # track_id 用規格第 3 節的規則
            assert t["track_id"] == uuid.uuid5(uuid.NAMESPACE_URL, f"cnc:{session}:{t['device_id']}:{t['channel_index']}")
            assert t["analysis_sample_rate"] == 44100 and t["analysis_status"] == "completed" and t["total_frames"] > 0
        by = {(t["device_name"], t["channel_index"]): t for t in res["tracks"]}
        a = by[("A · 錄音者 A", 0)]
        assert a["reported_sample_rate"] == 44100 and a["actual_sample_rate"] == 48000 and a["original_sample_rate"] == 48000, a
        assert a["requested_sample_rate"] == 48000 and a["audio_asset_id"] == f"{session}/{pids[0]}"
        assert a["source_checksum"] == hashlib.sha256(dev_mono_opus()["audio"][0]).hexdigest()
        assert by[("B · 錄音者 B", 0)]["actual_sample_rate"] == 44100
        # 每個成功音軌的 URL 都對得到實際存在的 PNG
        for t in res["tracks"]:
            for kind in ("spectrogram", "mfcc"):
                assert t[f"{kind}_url"] == f"/api/v1/sessions/{session}/analysis/{s['run_id']}/tracks/{t['track_id']}/{kind}.png"
                got = q(admin, "SELECT content FROM mobile_capture.track_analysis_artifacts WHERE run_id=%s AND track_id=%s AND kind=%s",
                        (s["run_id"], t["track_id"], kind))
                assert len(got) == 1 and bytes(got[0]["content"]).startswith(PNG) and len(got[0]["content"]) > 5000
        # Left／Right 各自分析：頻譜峰值分別在 440 Hz 與 1000 Hz
        freqs = np.arange(1025) * 44100 / 2048
        peak = lambda t: float(freqs[int(np.argmax(matrices(admin, s["run_id"], t["track_id"])["spectrogram"].mean(axis=1)))])  # noqa: E731
        assert abs(peak(by[("B · 錄音者 B", 0)]) - 440) < 25 and abs(peak(by[("B · 錄音者 B", 1)]) - 1000) < 25
        assert abs(peak(a) - 700) < 25 and abs(peak(by[("C · 錄音者 C", 0)]) - 2000) < 25
        # 同一 run 共用時間軸與 MFCC 色階。時間軸到最長那一軌的結尾（和網站內建分析同一個定義）；色階是所有成功音軌的 min/max
        longest = max(t["duration_seconds"] for t in res["tracks"])
        assert res["time_range"] == [0.0, longest] and res["duration_seconds"] == longest
        assert all(0.0 <= t["valid_range"][0] and t["valid_range"][1] <= t["duration_seconds"] + 1e-9 for t in res["tracks"])
        m = [matrices(admin, s["run_id"], t["track_id"])["mfcc"] for t in res["tracks"]]
        assert abs(res["mfcc_color_range"][0] - min(x.min() for x in m)) < 1e-3
        assert abs(res["mfcc_color_range"][1] - max(x.max() for x in m)) < 1e-3
        z = matrices(admin, s["run_id"], a["track_id"])
        assert sorted(z.files) == ["mfcc", "spectrogram", "times", "valid_range"]
        assert z["spectrogram"].shape[0] == 1025 and z["mfcc"].shape[0] == 20 and z["spectrogram"].shape[1] == z["mfcc"].shape[1] == len(z["times"])
        assert input_digest(admin) == before                    # 原始錄音、錄音紀錄、加工條件都沒被改


def test_three_mono_give_3_plus_3_and_three_stereo_give_6_plus_6():
    """規格 11：三台 Mono 得到 3＋3 張；三台 Stereo 得到 6＋6 張。"""
    with fresh_db() as (admin, writer):
        monos = [{**dev_mono_wav(), "name": f"Mono {i}"} for i in range(3)]
        stereos = [{**dev_stereo_aac(), "name": f"Stereo {i}"} for i in range(3)]
        for devices, n in ((monos, 3), (stereos, 6)):
            session, _ = seed(admin, devices)
            s = run(writer, session, matrices="never")
            assert s["status"] == "completed" and s["tracks_completed"] == n, s
            kinds = q(admin, "SELECT kind, count(*) AS n FROM mobile_capture.track_analysis_artifacts WHERE run_id=%s GROUP BY kind", (s["run_id"],))
            assert {k["kind"]: k["n"] for k in kinds} == {"spectrogram": n, "mfcc": n}, kinds       # --matrices never：不寫矩陣
            labels = q(admin, "SELECT channel_label, count(*) AS n FROM mobile_capture.recording_tracks WHERE session_id=%s GROUP BY 1", (session,))
            expect = {"Mono": 3} if n == 3 else {"Left": 3, "Right": 3}
            assert {r["channel_label"]: r["n"] for r in labels} == expect, labels


def test_builtin_worker_never_sees_a_claimable_row():
    """規格 7.1：外部結果只以最終狀態出現；不動內建工作；寫到一半失敗不留下半套。"""
    with fresh_db() as (admin, writer):
        session, _ = seed(admin, [dev_mono_wav()])
        builtin = uuid.uuid4()
        with psycopg.connect(admin) as c:
            c.execute("INSERT INTO mobile_capture.track_analysis_runs(id,session_id,fingerprint,start_seconds,status) VALUES(%s,%s,'builtin-fp',0,'queued')",
                      (builtin, session))
        run(writer, session)
        rows = q(admin, "SELECT id,status,fingerprint,result FROM mobile_capture.track_analysis_runs ORDER BY created_at")
        assert len(rows) == 2
        assert rows[0]["id"] == builtin and rows[0]["status"] == "queued" and rows[0]["result"] == {}       # 內建工作原封不動
        assert rows[1]["status"] == "completed" and rows[1]["fingerprint"] != "builtin-fp"
        assert q(admin, "SELECT count(*) AS n FROM mobile_capture.track_analysis_runs WHERE status IN ('queued','running') AND fingerprint LIKE 'ext:%%'")[0]["n"] == 0
        # publish 拒絕非最終狀態、別人的 fingerprint、對不上的 result、非 PNG
        with worker.connect(writer) as conn:
            base = dict(session_id=session, run_id=uuid.uuid4(), fingerprint="ext:mirdc-onprem:x", start_seconds=0.0,
                        end_seconds=None, tracks=[], artifacts=[])
            for bad in ({"status": "running", "result": {}}, {"status": "queued", "result": {}},
                        {"status": "completed", "fingerprint": "builtin-fp", "result": {}},
                        {"status": "completed", "result": {"run_id": "other", "session_id": str(session), "status": "completed"}}):
                try:
                    pub.publish(conn, **{**base, **bad})
                except pub.PublishError:
                    pass
                else:
                    raise AssertionError(f"應該拒絕：{bad}")
        # 寫到一半被資料庫拒絕：整筆回復
        session2, pids2 = seed(admin, [dev_mono_wav()])
        with worker.connect(writer) as conn:
            rid, tid = uuid.uuid4(), pub.track_uuid(session2, pids2[0], 0)
            track = {"track_id": tid, "device_id": pids2[0], "device_name": "x", "channel_index": 0, "channel_label": "Mono",
                     "source_channel_count": 1, "requested_sample_rate": None, "original_sample_rate": 44100,
                     "actual_sample_rate": 44100, "analysis_sample_rate": 44100, "duration_seconds": -1.0,   # 違反 CHECK
                     "total_frames": 10, "analysis_status": "completed"}
            result = {"run_id": str(rid), "session_id": str(session2), "status": "completed", "analyzable_track_count": 1, "tracks": [{
                "track_id": str(tid), "session_id": str(session2), "analysis_status": "completed",
                "spectrogram_url": pub.artifact_url(session2, rid, tid, "spectrogram"),
                "mfcc_url": pub.artifact_url(session2, rid, tid, "mfcc")}]}
            try:                                             # 內容一致、通過事前檢查，但資料庫在寫音軌時拒絕
                pub.publish(conn, session_id=session2, run_id=rid, fingerprint="ext:mirdc-onprem:y", start_seconds=0.0,
                            end_seconds=None, status="completed", result=result, tracks=[track],
                            artifacts=[(tid, "spectrogram", PNG + b"x"), (tid, "mfcc", PNG + b"y")])
            except psycopg.Error:
                pass
            else:
                raise AssertionError("違反資料庫約束時應該失敗")
        assert q(admin, "SELECT count(*) AS n FROM mobile_capture.track_analysis_runs WHERE session_id=%s", (session2,))[0]["n"] == 0
        assert q(admin, "SELECT count(*) AS n FROM mobile_capture.recording_tracks WHERE session_id=%s", (session2,))[0]["n"] == 0


def test_same_inputs_do_not_duplicate():
    """規格 7.6、11：相同 run 重送結果不重複。"""
    with fresh_db() as (admin, writer):
        session, _ = seed(admin, [dev_stereo_aac()])
        first = run(writer, session)
        count = lambda: (q(admin, "SELECT count(*) AS n FROM mobile_capture.track_analysis_runs")[0]["n"],  # noqa: E731
                         q(admin, "SELECT count(*) AS n FROM mobile_capture.track_analysis_artifacts")[0]["n"],
                         q(admin, "SELECT count(*) AS n FROM mobile_capture.recording_tracks")[0]["n"])
        assert count() == (1, 6, 2)
        again = run(writer, session)
        assert again["skipped"] is True and again["run_id"] == first["run_id"] and count() == (1, 6, 2)
        forced = run(writer, session, force=True)
        assert forced["skipped"] is False and forced["run_id"] == first["run_id"] and count() == (1, 6, 2)
        # 不同區間是另一筆工作，不覆寫整段的結果
        part = run(writer, session, start_seconds=1.0, end_seconds=2.0)
        assert part["run_id"] != first["run_id"] and count() == (2, 12, 2)


def test_corrupt_source_gives_partial_and_no_fake_tracks():
    """規格 6.4、11：部分失敗保留其他成功聲道；失敗來源有明確狀態；不產生假圖。"""
    with fresh_db() as (admin, writer):
        bad = {**dev_stereo_aac(), "corrupt": True}
        session, pids = seed(admin, [dev_mono_wav(), bad])
        s = run(writer, session)
        assert s["status"] == "partial" and s["tracks_completed"] == 1 and s["source_errors"] == 1, s
        res = q(admin, "SELECT result FROM mobile_capture.track_analysis_runs")[0]["result"]
        assert res["status"] == "partial" and len(res["tracks"]) == 1 and res["tracks"][0]["device_name"] == "A · 錄音者 C"
        assert res["completed_device_count"] == 2          # 已封存的裝置數（網站內建分析的定義），壞掉的那台也算已封存
        err = res["source_errors"][0]
        assert err["device_id"] == str(pids[1]) and err["device_name"] == "B · 錄音者 B" and err["status"] == "failed"
        assert "SHA-256" in err["error"] and ":" not in err["error"].replace("SHA-256", "")      # 不含地端路徑
        assert q(admin, "SELECT count(*) AS n FROM mobile_capture.recording_tracks WHERE device_id=%s", (pids[1],))[0]["n"] == 0
        assert q(admin, "SELECT count(*) AS n FROM mobile_capture.track_analysis_artifacts a JOIN mobile_capture.recording_tracks t "
                        "ON t.track_id=a.track_id WHERE t.device_id=%s", (pids[1],))[0]["n"] == 0


def test_missing_asset_then_late_asset_schedules_a_new_complete_run():
    """規格 7.7：晚到的裝置補封存會改變來源集合，要再排一次完整分析；先前的 partial 不當成最終結果。"""
    with fresh_db() as (admin, writer):
        late = {**dev_stereo_aac(), "audio": None}
        session, pids = seed(admin, [dev_mono_wav(), late])
        with worker.connect(writer) as conn:
            assert worker.pending_sessions(conn) == [session]
        s1 = run(writer, session)
        res1 = q(admin, "SELECT result FROM mobile_capture.track_analysis_runs")[0]["result"]
        assert s1["status"] == "partial" and res1["source_errors"][0]["status"] == "missing" and res1["source_errors"][0]["device_id"] == str(pids[1])
        assert res1["completed_device_count"] == 1
        with worker.connect(writer) as conn:
            assert worker.pending_sessions(conn) == []           # 同一批來源已有結果：不自動重跑
        with psycopg.connect(admin) as c:
            add_asset(c, session, pids[1], dev_stereo_aac()["audio"])
        with worker.connect(writer) as conn:
            assert worker.pending_sessions(conn) == [session]    # 來源集合變了：重新排入
        s2 = run(writer, session)
        assert s2["status"] == "completed" and s2["run_id"] != s1["run_id"] and s2["tracks_completed"] == 3
        rows = q(admin, "SELECT status FROM mobile_capture.track_analysis_runs ORDER BY created_at")
        assert [r["status"] for r in rows] == ["partial", "completed"]      # 舊的 partial 保留，新的在後面（API 取最新建立的）


def test_all_sources_failing_gives_failed_without_artifacts():
    with fresh_db() as (admin, writer):
        garbage = {"name": "錄音者 A", "audio": (b"this is not audio" * 500, "audio/webm"), "reported_sr": 48000, "reported_ch": 1}
        session, _ = seed(admin, [garbage])
        s = run(writer, session)
        assert s["status"] == "failed" and s["tracks_total"] == 0 and s["artifacts"] == 0, s
        row = q(admin, "SELECT status, result FROM mobile_capture.track_analysis_runs")[0]
        assert row["status"] == "failed" and row["result"]["tracks"] == [] and row["result"]["time_range"] == [0.0, 1.0]
        assert row["result"]["mfcc_color_range"] == [-1.0, 1.0] and row["result"]["duration_seconds"] == 0     # 和網站內建分析相同的預設值
        assert row["result"]["source_errors"][0]["error"] == "原始檔無法解碼"
        assert q(admin, "SELECT count(*) AS n FROM mobile_capture.track_analysis_artifacts")[0]["n"] == 0
        assert q(admin, "SELECT count(*) AS n FROM mobile_capture.recording_tracks")[0]["n"] == 0


def test_interval_with_a_shorter_track_reports_no_data():
    """規格 6.4：已解碼但區間內資料不足 → no_data、附 error、圖 URL 為 null；整段的摘要不被區間結果改掉。"""
    with fresh_db() as (admin, writer):
        short = {**dev_mono_wav(1.5, "mono_wav_short"), "name": "錄音者 A"}
        session, _ = seed(admin, [short, dev_stereo_aac()])
        whole = run(writer, session)
        assert whole["status"] == "completed"
        s = run(writer, session, start_seconds=2.0, end_seconds=3.5)
        assert s["status"] == "partial" and s["tracks_completed"] == 2 and s["tracks_total"] == 3, s
        row = q(admin, "SELECT start_seconds,end_seconds,result FROM mobile_capture.track_analysis_runs WHERE id=%s", (s["run_id"],))[0]
        assert row["start_seconds"] == 2.0 and row["end_seconds"] == 3.5 and row["result"]["time_range"] == [2.0, 3.5]
        nd = [t for t in row["result"]["tracks"] if t["analysis_status"] == "no_data"]
        assert len(nd) == 1 and nd[0]["device_name"] == "A · 錄音者 A" and nd[0]["spectrogram_url"] is None and nd[0]["mfcc_url"] is None and nd[0]["error"]
        assert q(admin, "SELECT count(*) AS n FROM mobile_capture.track_analysis_artifacts WHERE run_id=%s AND track_id=%s",
                 (s["run_id"], nd[0]["track_id"]))[0]["n"] == 0
        ok = [t for t in row["result"]["tracks"] if t["analysis_status"] == "completed"]
        assert all(2.0 <= t["valid_range"][0] and t["valid_range"][1] <= 3.5 + 1e-9 for t in ok), ok
        z = matrices(admin, s["run_id"], ok[0]["track_id"])
        assert abs(z["times"][0] - (2.0 + 1024 / 44100)) < 1e-9 and z["times"][-1] < 3.5     # times 是每個窗的中心
        summary = q(admin, "SELECT analysis_status FROM mobile_capture.recording_tracks WHERE track_id=%s", (nd[0]["track_id"],))[0]
        assert summary["analysis_status"] == "completed"
        for bad in ({"start_seconds": -1.0}, {"start_seconds": 3.0, "end_seconds": 2.0}):
            try:
                run(writer, session, **bad)
            except ValueError:
                pass
            else:
                raise AssertionError("不合法的區間應該拒絕")


def test_existing_track_id_is_reused():
    """規格第 3 節：資料庫已有同一音軌的 track_id 時沿用，不建立第二個 ID。"""
    with fresh_db() as (admin, writer):
        session, pids = seed(admin, [dev_mono_wav()])
        legacy = uuid.uuid4()
        with psycopg.connect(admin) as c:
            c.execute("INSERT INTO mobile_capture.recording_tracks(track_id,session_id,device_id,device_name,channel_index,channel_label,"
                      "source_channel_count,original_sample_rate,actual_sample_rate,analysis_sample_rate,duration_seconds,total_frames,analysis_status) "
                      "VALUES(%s,%s,%s,'舊名稱',0,'Mono',1,44100,44100,44100,4.0,176400,'failed')", (legacy, session, pids[0]))
        s = run(writer, session)
        res = q(admin, "SELECT result FROM mobile_capture.track_analysis_runs")[0]["result"]
        assert res["tracks"][0]["track_id"] == str(legacy) and str(legacy) in res["tracks"][0]["spectrogram_url"]
        rows = q(admin, "SELECT track_id, analysis_status FROM mobile_capture.recording_tracks")
        assert len(rows) == 1 and rows[0]["track_id"] == legacy and rows[0]["analysis_status"] == "completed"
        assert q(admin, "SELECT count(*) AS n FROM mobile_capture.track_analysis_artifacts WHERE run_id=%s AND track_id=%s", (s["run_id"], legacy))[0]["n"] == 3
        # 已知限制：資料庫裡若有不是照 uuid5 規則產生的舊 track_id，地端照規格沿用它；
        # 但內建 worker 一律自己算 uuid5 再寫入，會撞到 (session, device, channel) 的唯一鍵而失敗。
        # 內建和地端都只會產生 uuid5 的 ID，所以這只會發生在有第三個寫入者的時候。
        t = res["tracks"][0]
        canonical = str(uuid.uuid5(uuid.NAMESPACE_URL, f"cnc:{session}:{pids[0]}:0"))
        with psycopg.connect(admin) as c:
            c.execute("SET search_path TO mobile_capture")
            try:
                c.execute(SITE_TRACK_UPSERT, tuple({**t, "track_id": canonical}[k] for k in SITE_TRACK_KEYS))
            except psycopg.errors.UniqueViolation:
                c.rollback()
            else:
                raise AssertionError("預期內建的寫法會撞到唯一鍵")
        assert [r["track_id"] for r in q(admin, "SELECT track_id FROM mobile_capture.recording_tracks")] == [legacy]


def test_writer_role_is_least_privilege():
    """規格第 10 節：能讀輸入、能寫三張結果表；不能改原始錄音、不能讀 token_hash、不能刪、不能做 DDL。"""
    with fresh_db() as (admin, writer):
        session, pids = seed(admin, [dev_mono_wav()])
        run(writer, session)
        denied = [
            "UPDATE mobile_capture.audio_chunks SET checksum = checksum",
            "DELETE FROM mobile_capture.audio_chunks",
            "UPDATE mobile_capture.audio_assets SET byte_count = byte_count",
            "UPDATE mobile_capture.participant_recordings SET interrupted = true",
            "UPDATE mobile_capture.recording_sessions SET conditions = '{}'",
            "SELECT token_hash FROM mobile_capture.room_participants",
            "SELECT * FROM mobile_capture.room_participants",
            "DELETE FROM mobile_capture.track_analysis_artifacts",
            "DELETE FROM mobile_capture.track_analysis_runs",
            "DELETE FROM mobile_capture.recording_tracks",
            "CREATE TABLE mobile_capture.x (a int)",
            "ALTER TABLE mobile_capture.recording_tracks ADD COLUMN x int",
            "INSERT INTO mobile_capture.audio_assets(session_id,participant_id,mime_type,chunk_count,byte_count,checksum) "
            "SELECT session_id,participant_id,'x',1,1,'x' FROM mobile_capture.audio_assets",
        ]
        for stmt in denied:
            with psycopg.connect(writer) as c:
                try:
                    c.execute(stmt)
                except (psycopg.errors.InsufficientPrivilege, psycopg.errors.UndefinedTable):
                    continue
                raise AssertionError(f"應該被拒絕：{stmt}")
        attrs = q(admin, "SELECT rolsuper, rolcreatedb, rolcreaterole, rolbypassrls FROM pg_roles WHERE rolname='track_analysis_writer'")[0]
        assert not any(attrs.values()), attrs
        # 重跑帳號腳本會收回以前多給的欄位權限
        with psycopg.connect(admin, autocommit=True) as c:
            c.execute("GRANT SELECT (token_hash) ON mobile_capture.room_participants TO track_analysis_writer")
            c.execute((ROOT / "deploy" / "track_analysis_writer_role.sql").read_text(encoding="utf-8"))
        assert q(admin, "SELECT has_column_privilege('track_analysis_writer','mobile_capture.room_participants','token_hash','SELECT') AS p")[0]["p"] is False
        # 腳本管不到的權限要列出來提醒：其他 schema 經由 PUBLIC 得到的表權限、可建物件的 schema、暫存表
        role_sql = (ROOT / "deploy" / "track_analysis_writer_role.sql").read_text(encoding="utf-8")

        def notices():
            got = []
            with psycopg.connect(admin, autocommit=True) as c:
                c.add_notice_handler(lambda d: got.append((d.severity, d.message_primary)))
                c.execute(role_sql)
            return got
        clean = notices()
        assert not any(sev == "WARNING" for sev, _ in clean), clean
        assert any("暫存表" in m for _, m in clean), clean
        with psycopg.connect(admin, autocommit=True) as c:
            c.execute("CREATE SCHEMA other; CREATE TABLE other.t (a int); GRANT USAGE ON SCHEMA other TO PUBLIC; GRANT SELECT ON other.t TO PUBLIC")
            c.execute("CREATE SCHEMA scratch; GRANT CREATE ON SCHEMA scratch TO track_analysis_writer")
        warned = [m for sev, m in notices() if sev == "WARNING"]
        assert any("1 張資料表" in m for m in warned) and any("1 個 schema" in m for m in warned), warned


def test_pending_ignores_unfinished_and_empty_sessions_and_dry_run_writes_nothing():
    with fresh_db() as (admin, writer):
        done, _ = seed(admin, [dev_mono_wav()])
        seed(admin, [dev_mono_wav()], status="recording")                       # 還在錄
        seed(admin, [{**dev_mono_wav(), "audio": None}])                        # 已結束但沒有任何封存
        interrupted, _ = seed(admin, [{**dev_mono_wav(), "interrupted": True}], status="interrupted")
        with worker.connect(writer) as conn:
            assert set(worker.pending_sessions(conn)) == {done, interrupted}
        with tempfile.TemporaryDirectory() as d:
            s = run(writer, done, dry_run=str(Path(d) / "out"))
            files = sorted(p.name for p in (Path(d) / "out").iterdir())
            assert s["dry_run"] and "result.json" in files and sum(f.endswith(".png") for f in files) == 2 and sum(f.endswith(".npz") for f in files) == 1
            saved = json.loads((Path(d) / "out" / "result.json").read_text(encoding="utf-8"))
            assert saved["status"] == "completed" and len(saved["tracks"]) == 1
        assert q(admin, "SELECT count(*) AS n FROM mobile_capture.track_analysis_runs")[0]["n"] == 0
        assert q(admin, "SELECT count(*) AS n FROM mobile_capture.recording_tracks")[0]["n"] == 0
        s = run(writer, interrupted)                                           # 中斷的錄音可以分析，但保留不完整標示
        res = q(admin, "SELECT result FROM mobile_capture.track_analysis_runs WHERE id=%s", (s["run_id"],))[0]["result"]
        assert res["tracks"][0]["interrupted"] is True
        try:
            run(writer, uuid.uuid4())
        except LookupError:
            pass
        else:
            raise AssertionError("不存在的 session 應該報錯")


def test_fingerprint_and_ids_are_deterministic_and_parameter_sensitive():
    a, b = uuid.uuid4(), uuid.uuid4()
    f = pub.make_fingerprint([(a, "c1"), (b, "c2")], 0.0, None, sc.PARAMETERS)
    assert f == pub.make_fingerprint([(b, "c2"), (a, "c1")], 0, None, sc.PARAMETERS)          # 與來源順序無關
    assert f != pub.make_fingerprint([(a, "c1"), (b, None)], 0.0, None, sc.PARAMETERS)        # 來源缺一個
    assert f != pub.make_fingerprint([(a, "c1"), (b, "c2")], 0.0, 5.0, sc.PARAMETERS)         # 區間不同
    assert f != pub.make_fingerprint([(a, "c1"), (b, "c2")], 0.0, None, {**sc.PARAMETERS, "algorithm_version": "other"})
    assert f == pub.make_fingerprint([(a, "c1"), (b, "c2")], -0.0, None, sc.PARAMETERS)       # -0.0 與 0.0 是同一個區間
    assert f.startswith(pub.FINGERPRINT_PREFIX) and len(f) == len(pub.FINGERPRINT_PREFIX) + 64
    s = uuid.uuid4()
    assert pub.run_uuid(s, f) == pub.run_uuid(s, f) != pub.run_uuid(uuid.uuid4(), f)
    assert pub.track_uuid(s, a, 1) == uuid.uuid5(uuid.NAMESPACE_URL, f"cnc:{s}:{a}:1")


# ---------- Codex 第一輪審查（2026-11-20）指出的問題，各補一個回歸測試 ----------

def test_published_result_is_never_replaced_without_force():
    """同一批輸入已有結果時，不加 force 一律不覆寫（不論新的結果比較好、比較差、或一樣）。
    兩個 worker 同時跑同一個 session、其中一個遇到暫時性錯誤時，先寫入的那一筆留著。"""
    with fresh_db() as (admin, writer):
        session, _ = seed(admin, [dev_stereo_aac()])
        first = run(writer, session)
        snapshot = lambda: (q(admin, "SELECT status, result FROM mobile_capture.track_analysis_runs WHERE id=%s", (first["run_id"],))[0],  # noqa: E731
                            q(admin, "SELECT count(*) AS n FROM mobile_capture.track_analysis_artifacts WHERE run_id=%s", (first["run_id"],))[0]["n"])
        before = snapshot()
        assert before[0]["status"] == "completed" and before[1] == 6
        # 第二個 worker：在第一個提交之前就通過了「還沒有結果」的檢查，接著解碼失敗
        real_existing, real_decode = worker.pub.existing_run, worker.src.decode_to_wav
        calls = {"n": 0}

        def stale_check(conn, sid, fp):
            calls["n"] += 1
            return None if calls["n"] == 1 else real_existing(conn, sid, fp)

        def broken(src_path, wav):
            raise src.SourceError("原始檔無法解碼")
        worker.pub.existing_run, worker.src.decode_to_wav = stale_check, broken
        try:
            second = run(writer, session)
        finally:
            worker.pub.existing_run, worker.src.decode_to_wav = real_existing, real_decode
        assert second["kept_existing"] is True and second["status"] == "completed" and second["this_attempt_status"] == "failed", second
        assert second["run_id"] == first["run_id"] and snapshot() == before          # 資料庫完全沒變
        # 用已發布的結果做出各種「這次的結果」，直接測發布規則
        rid = uuid.UUID(first["run_id"])
        fp = q(admin, "SELECT fingerprint FROM mobile_capture.track_analysis_runs WHERE id=%s", (rid,))[0]["fingerprint"]
        stored = before[0]["result"]
        rows = {str(r["track_id"]): r for r in q(admin, "SELECT * FROM mobile_capture.recording_tracks")}
        pngs = {(str(r["track_id"]), r["kind"]): bytes(r["content"]) for r in q(
            admin, "SELECT track_id, kind, content FROM mobile_capture.track_analysis_artifacts WHERE run_id=%s AND kind<>'matrices'", (rid,))}

        def attempt(ok_tracks, source_errors=(), force=False):
            """ok_tracks：這次成功的音軌數（0–2）。回傳 publish() 的結果。"""
            tracks, arts, rtracks = [], [], []
            for i, t in enumerate(stored["tracks"]):
                good = i < ok_tracks
                rt = dict(t) if good else {**t, "analysis_status": "no_data", "spectrogram_url": None, "mfcc_url": None}
                rtracks.append(rt)
                row = {k: v for k, v in rows[t["track_id"]].items() if k != "session_id"}
                tracks.append({**row, "analysis_status": rt["analysis_status"]})
                if good:
                    arts += [(row["track_id"], k, pngs[(t["track_id"], k)]) for k in ("spectrogram", "mfcc")]
            status = "failed" if ok_tracks == 0 else ("completed" if ok_tracks == 2 and not source_errors else "partial")
            result = {**stored, "status": status, "tracks": rtracks, "analyzable_track_count": ok_tracks, "source_errors": list(source_errors)}
            with worker.connect(writer) as conn:
                return pub.publish(conn, session_id=session, run_id=rid, fingerprint=fp, start_seconds=0.0, end_seconds=None,
                                   status=status, result=result, tracks=tracks, artifacts=arts, force=force)

        state = lambda: (lambda r: (r["status"], r["result"]["analyzable_track_count"]))(  # noqa: E731
            q(admin, "SELECT status, result FROM mobile_capture.track_analysis_runs WHERE id=%s", (rid,))[0])
        err = [{"device_id": "x", "device_name": "x", "status": "failed", "error": "x"}]
        arts = lambda: q(admin, "SELECT count(*) AS n FROM mobile_capture.track_analysis_artifacts WHERE run_id=%s", (rid,))[0]["n"]  # noqa: E731
        # 已有 completed：不加 force，什麼都蓋不掉（較差、相同都一樣）
        for n, e in ((1, ()), (0, ()), (2, err), (2, ())):
            assert attempt(n, e) is False and state() == ("completed", 2) and arts() == 6, (n, e)
        assert snapshot() == before
        # 加 force 才會取代，而且取代的是同一筆
        assert attempt(1, force=True) is True and state() == ("partial", 1)
        # 已有 partial：較好的、成功音軌更多的、數量相同但成功的是另一條音軌的，不加 force 都不覆寫
        assert attempt(2) is False and state() == ("partial", 1)
        assert attempt(2, err) is False and state() == ("partial", 1)
        stored_tracks = stored["tracks"]                      # 數量相同、成功的是另一條音軌（Codex 第三輪 P1 的反例）
        stored["tracks"] = list(reversed(stored_tracks))
        try:
            assert attempt(1) is False and state() == ("partial", 1)
            kept = q(admin, "SELECT result FROM mobile_capture.track_analysis_runs WHERE id=%s", (rid,))[0]["result"]
            done_ids = [t["track_id"] for t in kept["tracks"] if t["analysis_status"] == "completed"]
            assert done_ids == [stored_tracks[0]["track_id"]], done_ids       # 先前成功的那一條還在
        finally:
            stored["tracks"] = stored_tracks
        assert attempt(0) is False and state() == ("partial", 1)
        assert attempt(0, force=True) is True and state() == ("failed", 0)
        assert attempt(2) is False and state() == ("failed", 0)                # 連 failed 也不會被自動取代
        assert attempt(2, force=True) is True and state() == ("completed", 2)
        assert q(admin, "SELECT count(*) AS n FROM mobile_capture.track_analysis_runs WHERE session_id=%s", (session,))[0]["n"] == 1


def test_existing_partial_is_kept_until_force():
    """worker 層：同一批輸入已有 partial 結果時，重跑不重算也不覆寫；加 --force 才重算。"""
    with fresh_db() as (admin, writer):
        session, _ = seed(admin, [dev_mono_wav(), {**dev_stereo_aac(), "corrupt": True}])
        first = run(writer, session)
        assert first["status"] == "partial" and first["skipped"] is False
        created = q(admin, "SELECT created_at FROM mobile_capture.track_analysis_runs")[0]["created_at"]
        real = worker.prepare_sources
        worker.prepare_sources = lambda *a, **k: (_ for _ in ()).throw(AssertionError("不應該重新解碼"))
        try:
            again = run(writer, session)
        finally:
            worker.prepare_sources = real
        assert again["skipped"] is True and again["kept_existing"] is True and again["status"] == "partial" and again["run_id"] == first["run_id"]
        forced = run(writer, session, force=True)
        assert forced["skipped"] is False and forced["status"] == "partial" and forced["run_id"] == first["run_id"]
        rows = q(admin, "SELECT created_at FROM mobile_capture.track_analysis_runs")
        assert len(rows) == 1 and rows[0]["created_at"] == created               # 取代的是同一筆，建立時間不變
        with worker.connect(writer) as conn:
            assert worker.pending_sessions(conn) == []


def test_decode_timeout_or_launch_failure_is_one_source_error_not_a_crash():
    """一個來源解碼逾時或解碼程式起不來：寫進 source_errors，其他來源照常發布。"""
    import subprocess as sp
    real = src.subprocess.run
    for exc, needle in ((sp.TimeoutExpired(cmd="ffmpeg", timeout=1), "上限"), (OSError("spawn failed C:/secret/path"), "無法啟動")):
        with fresh_db() as (admin, writer):
            session, pids = seed(admin, [dev_mono_wav(), dev_stereo_aac()])
            n = {"calls": 0}

            def flaky(*a, **kw):
                n["calls"] += 1
                if n["calls"] == 2:
                    raise exc
                return real(*a, **kw)
            src.subprocess.run = flaky
            try:
                s = run(writer, session)
            finally:
                src.subprocess.run = real
            assert s["status"] == "partial" and s["tracks_completed"] == 1 and s["source_errors"] == 1, s
            err = q(admin, "SELECT result FROM mobile_capture.track_analysis_runs")[0]["result"]["source_errors"][0]
            assert err["device_id"] == str(pids[1]) and needle in err["error"] and "secret" not in err["error"], err


def test_publish_refuses_autocommit_and_images_that_do_not_match_the_result():
    with fresh_db() as (admin, writer):
        session, pids = seed(admin, [dev_mono_wav()])
        rid, tid = uuid.uuid4(), pub.track_uuid(session, pids[0], 0)
        track = {"track_id": tid, "device_id": pids[0], "device_name": "x", "channel_index": 0, "channel_label": "Mono",
                 "source_channel_count": 1, "requested_sample_rate": None, "original_sample_rate": 44100,
                 "actual_sample_rate": 44100, "analysis_sample_rate": 44100, "duration_seconds": 4.0,
                 "total_frames": 176400, "analysis_status": "completed"}
        good_track = {"track_id": str(tid), "session_id": str(session), "analysis_status": "completed",
                      "spectrogram_url": pub.artifact_url(session, rid, tid, "spectrogram"),
                      "mfcc_url": pub.artifact_url(session, rid, tid, "mfcc")}
        res = lambda t: {"run_id": str(rid), "session_id": str(session), "status": "completed", "tracks": [t],  # noqa: E731
                         "analyzable_track_count": 1 if t["analysis_status"] == "completed" else 0}
        nodata = {**good_track, "analysis_status": "no_data", "spectrogram_url": None, "mfcc_url": None}
        nodata_row = {**track, "analysis_status": "no_data"}
        failed_base = lambda **kw: {**base, "status": "failed", **kw}  # noqa: E731
        both = [(tid, "spectrogram", PNG + b"a"), (tid, "mfcc", PNG + b"b")]
        base = dict(session_id=session, run_id=rid, fingerprint="ext:mirdc-onprem:z", start_seconds=0.0, end_seconds=None,
                    status="completed", tracks=[track])
        cases = [
            ("完成的音軌沒有任何圖", res(good_track), []),
            ("少一張 mfcc", res(good_track), both[:1]),
            ("URL 指到別的 run", res({**good_track, "mfcc_url": good_track["mfcc_url"].replace(str(rid), str(uuid.uuid4()))}), both),
            ("no_data 的音軌卻有圖", res({**good_track, "analysis_status": "no_data", "spectrogram_url": None, "mfcc_url": None}), both),
            ("no_data 的音軌卻有 URL", res({**good_track, "analysis_status": "no_data"}), []),
            ("同一張圖給兩次", res(good_track), both + both[:1]),
            ("成功音軌數寫錯", {**res(good_track), "analyzable_track_count": 2}, both),
            ("沒有成功音軌數", {k: v for k, v in res(good_track).items() if k != "analyzable_track_count"}, both),
            ("要寫的音軌沒有列在 result.tracks", {**res(good_track), "tracks": [], "analyzable_track_count": 0}, []),
            ("completed 卻帶著來源錯誤", {**res(good_track), "source_errors": [{"device_id": "x"}]}, both),
        ]
        with worker.connect(writer) as conn:
            for name, result, arts in cases:
                try:
                    pub.publish(conn, result=result, artifacts=arts, **base)
                except pub.PublishError:
                    continue
                raise AssertionError(f"應該拒絕：{name}")
            # 沒有成功的音軌：不能帶任何 artifact（含矩陣），音軌列的狀態也要一致
            failed_res = {**res(nodata), "status": "failed"}
            for name, kw in (("no_data 的音軌帶矩陣", dict(result=failed_res, tracks=[nodata_row], artifacts=[(tid, "matrices", b"npz")])),
                             ("音軌列說 completed、result 說 no_data", dict(result=failed_res, tracks=[track], artifacts=[])),
                             ("狀態寫 partial 但沒有任何成功音軌", dict(result={**failed_res, "status": "partial"}, tracks=[nodata_row], artifacts=[], status="partial"))):
                try:
                    pub.publish(conn, **failed_base(**kw))
                except pub.PublishError:
                    continue
                raise AssertionError(f"應該拒絕：{name}")
        with psycopg.connect(writer, autocommit=True, row_factory=psycopg.rows.dict_row) as conn:
            try:
                pub.publish(conn, result=res(good_track), artifacts=both, **base)
            except pub.PublishError as e:
                assert "autocommit" in str(e)
            else:
                raise AssertionError("autocommit 連線應該拒絕")
        assert q(admin, "SELECT count(*) AS n FROM mobile_capture.track_analysis_runs")[0]["n"] == 0
        assert q(admin, "SELECT count(*) AS n FROM mobile_capture.recording_tracks")[0]["n"] == 0
        with worker.connect(writer) as conn:                    # 對得上的才寫得進去
            assert pub.publish(conn, result=res(good_track), artifacts=both, **base) is True
        assert q(admin, "SELECT count(*) AS n FROM mobile_capture.track_analysis_artifacts")[0]["n"] == 2


def test_chunk_without_checksum_is_rejected():
    """音段沒有 SHA-256 紀錄時不能當成已驗證。正式 schema 的 checksum 是 NOT NULL，這裡是多一層防護。"""
    data = b"abc" * 100

    class Cur:
        itersize = 0

        def __init__(self, rows):
            self.rows = rows

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def execute(self, *a):
            pass

        def __iter__(self):
            return iter(self.rows)

    class Conn:
        def __init__(self, rows):
            self.rows = rows

        def cursor(self, name=None):
            return Cur(self.rows)

    asset = {"chunk_count": 1, "byte_count": len(data), "checksum": hashlib.sha256(data).hexdigest()}
    with tempfile.TemporaryDirectory() as d:
        ok = [{"chunk_index": 0, "audio_data": data, "checksum": hashlib.sha256(data).hexdigest()}]
        src.rebuild_asset(Conn(ok), uuid.uuid4(), uuid.uuid4(), asset, Path(d) / "a.bin")
        assert (Path(d) / "a.bin").read_bytes() == data
        for bad_checksum in (None, ""):
            rows = [{"chunk_index": 0, "audio_data": data, "checksum": bad_checksum}]
            try:
                src.rebuild_asset(Conn(rows), uuid.uuid4(), uuid.uuid4(), asset, Path(d) / "b.bin")
            except src.SourceError as e:
                assert "沒有 SHA-256" in str(e)
            else:
                raise AssertionError("沒有 checksum 的音段應該拒絕")


def test_other_sample_rates_are_analysed_like_the_builtin():
    """網站內建分析不限 44100／48000，其他取樣率照樣重取樣後分析；地端要一致，不能把這種來源當成失敗。"""
    with fresh_db() as (admin, writer):
        dev = {"name": "錄音者 A", "audio": encode("mono_wav_16k", tone(1500, 3.0, 16000), 16000, "wav"), "reported_sr": 48000, "reported_ch": 1}
        session, _ = seed(admin, [dev])
        s = run(writer, session)
        assert s["status"] == "completed" and s["tracks_completed"] == 1, s
        res = q(admin, "SELECT result FROM mobile_capture.track_analysis_runs")[0]["result"]
        t = res["tracks"][0]
        assert t["actual_sample_rate"] == 16000 and t["analysis_sample_rate"] == 44100 and t["total_frames"] == 48000
        assert t["duration_seconds"] == 3.0 and res["time_range"] == [0.0, 3.0]
        z = matrices(admin, s["run_id"], t["track_id"])
        freqs = np.arange(1025) * 44100 / 2048
        assert abs(float(freqs[int(np.argmax(z["spectrogram"].mean(axis=1)))]) - 1500) < 25


# ---------- Codex 第五輪審查（2026-11-20）：一個來源或一個聲道出問題，不能拖垮同一批的其他來源 ----------

def test_one_channel_failing_does_not_block_the_others():
    """某個聲道算不出來、或圖畫不出來：只有那個聲道標成 failed，其他照常發布（和網站內建分析相同）。"""
    real_analyze, real_mfcc = worker.sc.analyze_channel, worker.render.mfcc_png
    for mode, message in (("analyze", "此聲道分析失敗"), ("mfcc", "圖表產生失敗")):
        with fresh_db() as (admin, writer):
            session, pids = seed(admin, [dev_mono_wav(), dev_stereo_aac()])
            n = {"calls": 0}

            def flaky(*a, **kw):
                n["calls"] += 1
                if n["calls"] == 3:                                # 第三個聲道＝Stereo 的 Right
                    raise MemoryError("simulated C:/secret/path")
                return (real_analyze if mode == "analyze" else real_mfcc)(*a, **kw)
            if mode == "analyze":
                worker.sc.analyze_channel = flaky
            else:
                worker.render.mfcc_png = flaky
            try:
                s = run(writer, session)
            finally:
                worker.sc.analyze_channel, worker.render.mfcc_png = real_analyze, real_mfcc
            assert s["status"] == "partial" and s["tracks_completed"] == 2 and s["tracks_total"] == 3 and s["source_errors"] == 0, (mode, s)
            res = q(admin, "SELECT result FROM mobile_capture.track_analysis_runs")[0]["result"]
            bad = [t for t in res["tracks"] if t["analysis_status"] == "failed"]
            assert len(bad) == 1 and bad[0]["channel_label"] == "Right" and bad[0]["error"] == message, (mode, bad)
            assert bad[0]["spectrogram_url"] is None and bad[0]["mfcc_url"] is None and "secret" not in json.dumps(res)
            assert q(admin, "SELECT count(*) AS n FROM mobile_capture.track_analysis_artifacts WHERE track_id=%s", (bad[0]["track_id"],))[0]["n"] == 0
            assert q(admin, "SELECT count(*) AS n FROM mobile_capture.track_analysis_artifacts")[0]["n"] == 6       # 另外兩軌各 3 個
            rows = q(admin, "SELECT channel_label, analysis_status FROM mobile_capture.recording_tracks ORDER BY device_name, channel_index")
            assert [(r["channel_label"], r["analysis_status"]) for r in rows] == [("Mono", "completed"), ("Left", "completed"), ("Right", "failed")]


def test_extreme_sample_rate_is_one_source_error():
    """取樣率很怪的檔案（重取樣要幾 GB 記憶體）：在配置記憶體之前就列為來源失敗，其他來源照常發布。"""
    with fresh_db() as (admin, writer):
        odd = {"name": "錄音者 B", "audio": encode("mono_wav_44099", tone(1000, 2.0, 44099), 44099, "wav"), "reported_sr": 48000, "reported_ch": 1}
        session, pids = seed(admin, [dev_mono_wav(), odd])
        s = run(writer, session)
        assert s["status"] == "partial" and s["tracks_completed"] == 1 and s["source_errors"] == 1, s
        res = q(admin, "SELECT result FROM mobile_capture.track_analysis_runs")[0]["result"]
        err = res["source_errors"][0]
        assert err["device_id"] == str(pids[1]) and err["status"] == "failed" and "44099" in err["error"] and "上限" in err["error"], err
        assert [t["device_name"] for t in res["tracks"]] == ["A · 錄音者 C"] and res["time_range"] == [0.0, 4.0]


def test_read_failure_after_decode_recomputes_the_shared_time_axis():
    """解碼成功的檔案後來讀不回來：那台列為來源失敗，共用時間軸只依實際有音軌的裝置決定（和網站內建分析相同）。"""
    real = src.read_wav
    with fresh_db() as (admin, writer):
        long_dev = {**dev_mono_wav(6.0, "mono_wav_long"), "name": "錄音者 A"}
        session, pids = seed(admin, [long_dev, dev_stereo_aac()])

        def flaky(path):
            if str(pids[0]) in str(path):
                raise src.SourceError("原始檔無法解碼")
            return real(path)
        src.read_wav = flaky
        try:
            s = run(writer, session)
        finally:
            src.read_wav = real
        assert s["status"] == "partial" and s["tracks_completed"] == 2 and s["source_errors"] == 1, s
        res = q(admin, "SELECT result FROM mobile_capture.track_analysis_runs")[0]["result"]
        assert res["source_errors"][0]["device_id"] == str(pids[0])
        longest = max(t["duration_seconds"] for t in res["tracks"])
        assert longest < 5.0 and res["time_range"] == [0.0, longest] and res["duration_seconds"] == longest     # 不是 6 秒
        assert q(admin, "SELECT count(*) AS n FROM mobile_capture.recording_tracks WHERE device_id=%s", (pids[0],))[0]["n"] == 0


# ---------- 用網站後端 backend/analysis.py 裡的 SQL 原文來讀寫 ----------
# 下面 SITE_ 開頭的 SQL 是從 backend/analysis.py 照抄的；test_site_sql_still_matches_the_backend 會檢查它們還在那個檔案裡。
SITE_GET_RUN = """SELECT * FROM track_analysis_runs WHERE session_id=%s AND start_seconds=%s
                AND end_seconds IS NOT DISTINCT FROM %s ORDER BY created_at DESC LIMIT 1"""
SITE_GET_IMAGE = """SELECT a.content FROM track_analysis_artifacts a JOIN track_analysis_runs r ON r.id=a.run_id
                WHERE r.session_id=%s AND a.run_id=%s AND a.track_id=%s AND a.kind=%s"""
SITE_CLAIM = "SELECT * FROM track_analysis_runs WHERE status='queued' ORDER BY created_at LIMIT 1 FOR UPDATE SKIP LOCKED"
SITE_TRACK_KEYS = ["track_id", "session_id", "device_id", "device_name", "channel_index", "channel_label", "source_channel_count",
                   "requested_sample_rate", "original_sample_rate", "actual_sample_rate", "analysis_sample_rate", "duration_seconds",
                   "total_frames", "analysis_status"]
SITE_TRACK_UPSERT = ("INSERT INTO recording_tracks(" + ",".join(SITE_TRACK_KEYS) + ") VALUES(" + ",".join(["%s"] * len(SITE_TRACK_KEYS))
                     + ") ON CONFLICT(track_id) DO UPDATE SET analysis_status=excluded.analysis_status")
# process_job 寫進 result 的欄位，以及每個音軌的欄位
SITE_RESULT_KEYS = {"session_id", "run_id", "status", "analysis_sample_rate", "tracks", "source_errors", "completed_device_count",
                    "analyzable_track_count", "duration_seconds", "time_range", "mfcc_color_range", "parameters", "versions"}
SITE_RESULT_TRACK_KEYS = set(SITE_TRACK_KEYS) | {"reported_sample_rate", "audio_asset_id", "source_checksum", "spectrogram_url",
                                                  "mfcc_url", "valid_range"}
SITE_PARAMETER_KEYS = {"analysis_sample_rate", "fft_size", "hop_length", "window", "mel_bands", "mfcc_count", "mel_scale", "dct",
                       "frequency_range", "spectrogram_scale", "db_reference", "mfcc_power", "frame_policy", "resampling",
                       "time_reference", "algorithm_version"}


def test_site_queries_read_the_external_result():
    """網站查詢 API、PNG API、內建 worker 用的 SQL，對著地端寫入的資料實際執行（資料表是網站的正式定義）。"""
    with fresh_db() as (admin, writer):
        session, pids = seed(admin, [dev_mono_wav(), dev_stereo_aac()])
        s = run(writer, session)
        part = run(writer, session, start_seconds=1.0, end_seconds=2.0)
        with psycopg.connect(admin, row_factory=psycopg.rows.dict_row) as c:
            c.execute("SET search_path TO mobile_capture")       # 網站後端的連線也是用這個 search_path
            c.commit()
            # 查詢 API：整段、區間各自找得到地端的結果；沒算過的區間找不到
            job = c.execute(SITE_GET_RUN, (session, 0, None)).fetchone()
            assert str(job["id"]) == s["run_id"] and job["status"] == "completed"
            assert str(c.execute(SITE_GET_RUN, (session, 1.0, 2.0)).fetchone()["id"]) == part["run_id"]
            assert c.execute(SITE_GET_RUN, (session, 1.0, 3.0)).fetchone() is None
            res = job["result"]
            # 內建分析寫的欄位，地端的結果都要有，前端才讀得到同樣的東西
            assert SITE_RESULT_KEYS <= set(res), SITE_RESULT_KEYS - set(res)
            assert SITE_PARAMETER_KEYS <= set(res["parameters"]), SITE_PARAMETER_KEYS - set(res["parameters"])
            assert all(not isinstance(v, dict) for v in res["parameters"].values())            # 單層，和內建分析同樣的形狀
            assert len(res["tracks"]) == 3
            for t in res["tracks"]:
                assert SITE_RESULT_TRACK_KEYS <= set(t), SITE_RESULT_TRACK_KEYS - set(t)
                # PNG API：URL 裡的 run_id／track_id 拿去查，真的拿得到 PNG
                for kind in ("spectrogram", "mfcc"):
                    parts = t[f"{kind}_url"].split("/")
                    assert parts[:5] == ["", "api", "v1", "sessions", str(session)] and parts[-1] == f"{kind}.png"
                    got = c.execute(SITE_GET_IMAGE, (session, parts[6], parts[8], kind)).fetchone()
                    assert bytes(got["content"]).startswith(PNG)
                other = uuid.uuid4()                                                            # 換一個 session 就拿不到
                assert c.execute(SITE_GET_IMAGE, (other, s["run_id"], t["track_id"], "spectrogram")).fetchone() is None
            # 內建 worker 領工作：地端寫的列它領不到
            assert c.execute(SITE_CLAIM).fetchone() is None
            c.rollback()
            # 主持人之後在網站按「分析」：內建 worker 用它自己的方式寫同一批音軌，不會撞在一起，也不會多出音軌
            before = c.execute("SELECT track_id, device_name FROM recording_tracks ORDER BY track_id").fetchall()
            for t in res["tracks"]:
                builtin_tid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"cnc:{session}:{t['device_id']}:{t['channel_index']}"))   # 內建自己算的 ID
                assert builtin_tid == t["track_id"]
                c.execute(SITE_TRACK_UPSERT, tuple({**t, "track_id": builtin_tid}[k] for k in SITE_TRACK_KEYS))
            builtin = uuid.uuid4()
            c.execute("INSERT INTO track_analysis_runs(id,session_id,fingerprint,start_seconds,end_seconds,status) VALUES(%s,%s,%s,%s,%s,'queued')",
                      (builtin, session, hashlib.sha256(b"builtin").hexdigest(), 0, None))
            c.commit()
            assert c.execute("SELECT track_id, device_name FROM recording_tracks ORDER BY track_id").fetchall() == before
            assert c.execute(SITE_CLAIM).fetchone()["id"] == builtin                            # 它領到的是它自己的那一筆
            c.rollback()
        # 之後地端再跑一次：內建的工作列不動，地端已有的結果照規則保留
        again = run(writer, session)
        assert again["skipped"] is True and again["run_id"] == s["run_id"]
        row = q(admin, "SELECT status, result FROM mobile_capture.track_analysis_runs WHERE id=%s", (builtin,))[0]
        assert row["status"] == "queued" and row["result"] == {}


def _squash(text):
    return "".join(text.split())


def test_site_sql_still_matches_the_backend():
    """這裡抄的查詢如果和 backend/analysis.py 不一樣了，上面的測試就不再代表網站的行為。"""
    source = _squash((ROOT / "backend" / "analysis.py").read_text(encoding="utf-8"))
    for name, text in (("查詢 API", SITE_GET_RUN), ("PNG API", SITE_GET_IMAGE), ("內建 worker 領工作", SITE_CLAIM)):
        assert _squash(text) in source, f"{name} 的 SQL 已經和 backend/analysis.py 不同"
    assert _squash("ON CONFLICT(track_id) DO UPDATE SET analysis_status=excluded.analysis_status") in source
    assert _squash("'track_id','session_id','device_id','device_name','channel_index','channel_label','source_channel_count',") in source
    assert _squash("f'cnc:{sid}:{device}:{index}'") in source                       # track_id 的規則
    assert _squash("f\"{source['source_position']} · {source['name']}\"") in source   # 顯示名稱的格式


def test_database_passes_the_sites_own_startup_check():
    """測試資料庫要通過網站啟動時的結構檢查（backend/schema.py），地端寫入之後也一樣。"""
    sys.path.insert(0, str(ROOT))
    from backend.schema import check_schema
    with fresh_db() as (admin, writer):
        session, _ = seed(admin, [dev_mono_wav()])
        run(writer, session)
        with psycopg.connect(admin, row_factory=psycopg.rows.dict_row) as c:
            target = check_schema(c)
            assert target["name"].startswith("track_test_")


def test_real_migration_constraints_are_in_force():
    """確認測試跑在網站的正式定義上，而不是放寬過的版本。"""
    with fresh_db() as (admin, _):
        cols = {(r["table_name"], r["column_name"]): r for r in q(admin, """
            SELECT table_name, column_name, data_type, is_nullable FROM information_schema.columns
            WHERE table_schema='mobile_capture'""")}
        assert cols[("participant_recordings", "source_position")]["data_type"] == "text"
        assert cols[("track_analysis_runs", "result")]["is_nullable"] == "NO"
        assert cols[("recording_sessions", "machine_id")]["data_type"] == "uuid"
        names = {r["conname"] for r in q(admin, "SELECT conname FROM pg_constraint")}
        assert "take_requires_machine" in names
        idx = {r["indexname"] for r in q(admin, "SELECT indexname FROM pg_indexes WHERE schemaname='mobile_capture'")}
        assert {"track_analysis_queue", "one_open_session"} <= idx


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
