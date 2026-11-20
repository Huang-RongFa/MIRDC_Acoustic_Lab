"""地端外部分析 worker：讀一個 session 的封存音檔，逐聲道算 Spectrogram／MFCC，寫回共用資料庫。

依據：《CNC Acoustic Lab｜外部音訊分析系統對接規格》（2026-11-17）。設計說明見 docs/external-track-analysis.md。

連線字串放環境變數（不要寫進指令或程式）：
    $env:TRACK_ANALYSIS_DATABASE_URL = 'postgresql://track_analysis_writer@<host>:5432/cnc_acoustic_lab?sslmode=require'
用法：
    python -X utf8 analysis/track_analysis/worker.py --session <session_id>                 # 整段
    python -X utf8 analysis/track_analysis/worker.py --session <session_id> --start 10 --end 20
    python -X utf8 analysis/track_analysis/worker.py --session <session_id> --dry-run D:/cnc_track/try1   # 不寫資料庫，結果存到資料夾
    python -X utf8 analysis/track_analysis/worker.py --pending --once                       # 處理所有還沒有外部結果的 session
"""
import argparse
import json
import logging
import os
import sys
import tempfile
import time
import uuid
from pathlib import Path

import numpy as np
import psycopg
from psycopg.rows import dict_row

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from track_analysis import publish as pub  # noqa: E402
from track_analysis import render  # noqa: E402
from track_analysis import signal_contract as sc  # noqa: E402
from track_analysis import source as src  # noqa: E402

log = logging.getLogger("track_analysis")
MATRICES_AUTO_LIMIT = 64 * 1024 * 1024       # --matrices auto：壓縮後超過這個大小就不寫進資料庫
CHANNEL_LABELS = {1: ("Mono",), 2: ("Left", "Right")}


def connect(url):
    c = psycopg.connect(url, row_factory=dict_row, connect_timeout=15)
    c.execute("SET statement_timeout = '300s'")
    c.execute("SET lock_timeout = '30s'")
    c.commit()
    return c


def _expected_end(frames_44k, start_seconds, end_seconds):
    """這個聲道在要求區間內，最後一個完整窗的結尾（錄音秒數）；資料不足一個窗時回傳 None。"""
    i0 = int(round(start_seconds * sc.ANALYSIS_SAMPLE_RATE))
    i1 = frames_44k if end_seconds is None else min(frames_44k, int(round(end_seconds * sc.ANALYSIS_SAMPLE_RATE)))
    n = i1 - i0
    if n < sc.FFT_SIZE:
        return None
    t = 1 + (n - sc.FFT_SIZE) // sc.HOP_LENGTH
    return start_seconds + ((t - 1) * sc.HOP_LENGTH + sc.FFT_SIZE) / sc.ANALYSIS_SAMPLE_RATE


def session_fingerprint(rows, start_seconds, end_seconds):
    return pub.make_fingerprint([(r["participant_id"], r["checksum"]) for r in rows],
                                start_seconds, end_seconds, sc.PARAMETERS)


def prepare_sources(conn, session_id, rows, work):
    """重建、驗證、解碼成暫存 wav。回傳 (devices, source_errors)。
    devices 只帶檔案路徑與格式資訊，不帶音訊；音訊之後一次只讀一台裝置，記憶體用量不隨裝置數增加。
    失敗或缺失的來源寫進 source_errors（規格 6.4），不影響其他來源。"""
    devices, errors = [], []
    for r in rows:
        ident = {"device_id": str(r["participant_id"]), "device_name": r["device_name"]}
        if r["checksum"] is None:
            errors.append({**ident, "status": "missing", "error": "這台裝置的音檔尚未封存"})
            continue
        raw = work / f"{r['participant_id']}.bin"
        wav = work / f"{r['participant_id']}.wav"
        try:
            src.rebuild_asset(conn, session_id, r["participant_id"], r, raw)
            sr, channels, frames = src.decode_to_wav(raw, wav)
            n44 = src.analysis_length(frames, sr)
        except src.SourceError as e:
            errors.append({**ident, "status": "failed", "error": str(e)})
            wav.unlink(missing_ok=True)
            continue
        finally:
            conn.rollback()                      # 結束讀取用的交易，不佔著連線
            raw.unlink(missing_ok=True)
        devices.append({"row": r, "wav": wav, "sample_rate": sr, "channels": channels, "frames": frames, "frames_44k": n44})
    return devices, errors


def analyse_session(conn, session_id, start_seconds=0.0, end_seconds=None, matrices="auto", force=False, dry_run=None):
    """分析一個 session 並寫回（或 dry_run 時寫到資料夾）。回傳摘要 dict。"""
    start_seconds = float(start_seconds) + 0.0
    if not start_seconds >= 0 or (end_seconds is not None and not float(end_seconds) > start_seconds):
        raise ValueError("區間不合法：start 必須 >= 0，end 必須大於 start")
    end_seconds = None if end_seconds is None else float(end_seconds)
    rows = src.list_sources(conn, session_id)
    conn.rollback()
    if not rows:
        raise LookupError(f"找不到 session {session_id}，或它沒有任何錄音者")
    fingerprint = session_fingerprint(rows, start_seconds, end_seconds)
    run_id = pub.run_uuid(session_id, fingerprint)
    if dry_run is None and not force:
        prev = pub.existing_run(conn, session_id, fingerprint)
        conn.rollback()
        if prev:                                            # 同一批輸入已有結果（不論狀態）：不重算、不覆寫；要重算請加 --force
            return {"session_id": str(session_id), "run_id": str(prev["id"]), "status": prev["status"], "skipped": True,
                    "kept_existing": True}
    known_ids = {} if dry_run is not None else pub.existing_track_ids(conn, session_id)
    conn.rollback()

    with tempfile.TemporaryDirectory(prefix="track_analysis_") as tmp:
        devices, source_errors = prepare_sources(conn, session_id, rows, Path(tmp))
        # 整批共用的時間軸（規格第 8 節）：由各聲道的長度算出，不必先把音訊讀進來
        ends = [e for d in devices for e in [_expected_end(d["frames_44k"], start_seconds, end_seconds)] if e is not None]
        time_range = [start_seconds, float(end_seconds if end_seconds is not None else max(ends))] if ends else None

        artifacts, track_rows, result_tracks, mfccs = [], [], [], {}
        for d in devices:                                   # 一次只處理一台裝置
            r, sr = d["row"], d["sample_rate"]
            try:
                data = src.read_wav(d["wav"])
            except src.SourceError as e:
                source_errors.append({"device_id": str(r["participant_id"]), "device_name": r["device_name"],
                                      "status": "failed", "error": str(e)})
                continue
            finally:
                d["wav"].unlink(missing_ok=True)
            for idx, label in enumerate(CHANNEL_LABELS[data.shape[1]]):
                pid = r["participant_id"]
                tid = known_ids.get((pid, idx)) or pub.track_uuid(session_id, pid, idx)
                duration = data.shape[0] / sr
                entry = {
                    "track_id": str(tid), "session_id": str(session_id), "device_id": str(pid),
                    "device_name": r["device_name"], "channel_index": idx, "channel_label": label,
                    "source_channel_count": data.shape[1],
                    "requested_sample_rate": r["requested_sample_rate"], "reported_sample_rate": r["reported_sample_rate"],
                    "original_sample_rate": sr, "actual_sample_rate": sr,
                    "analysis_sample_rate": sc.ANALYSIS_SAMPLE_RATE, "duration_seconds": duration,
                    "total_frames": int(data.shape[0]), "audio_asset_id": f"{session_id}/{pid}",
                    "source_checksum": r["checksum"], "interrupted": bool(r["interrupted"]),
                    "analysis_status": "no_data", "spectrogram_url": None, "mfcc_url": None}
                try:
                    a = sc.analyze_channel(np.ascontiguousarray(data[:, idx]), sr, start_seconds, end_seconds)
                except sc.NoData:
                    entry["error"] = "這個區間內的資料不足一個完整的分析窗"
                else:
                    title = f"{r['device_name']}｜{label}"
                    artifacts.append((tid, "spectrogram", render.spectrogram_png(a["spectrogram_db"], a["times"], time_range, title)))
                    if matrices == "always" or (matrices == "auto" and a["spectrogram_db"].nbytes <= 8 * MATRICES_AUTO_LIMIT):
                        npz = render.matrices_npz(a["spectrogram_db"], a["mfcc"], a["times"], a["valid_range"])
                        if matrices == "always" or len(npz) <= MATRICES_AUTO_LIMIT:
                            artifacts.append((tid, "matrices", npz))
                            entry["matrices_stored"] = True
                        del npz
                    if not entry.get("matrices_stored"):
                        entry["matrices_stored"] = False
                        if matrices == "auto":
                            entry["matrices_note"] = "矩陣超過自動上限，未寫入資料庫"
                    mfccs[tid] = (a["mfcc"], a["times"], title)
                    entry.update({"analysis_status": "completed", "valid_range": [float(v) for v in a["valid_range"]],
                                  "spectrogram_url": pub.artifact_url(session_id, run_id, tid, "spectrogram"),
                                  "mfcc_url": pub.artifact_url(session_id, run_id, tid, "mfcc")})
                    del a
                result_tracks.append(entry)
                track_rows.append({
                    "track_id": tid, "device_id": pid, "device_name": r["device_name"],
                    "channel_index": idx, "channel_label": label, "source_channel_count": data.shape[1],
                    "requested_sample_rate": r["requested_sample_rate"], "original_sample_rate": sr,
                    "actual_sample_rate": sr, "analysis_sample_rate": sc.ANALYSIS_SAMPLE_RATE,
                    "duration_seconds": duration, "total_frames": int(data.shape[0]),
                    "analysis_status": entry["analysis_status"]})
            del data

    # MFCC 色階：同一 run 所有成功音軌共用 min/max，不逐張正規化（規格第 8 節）
    color_range = None
    if mfccs:
        color_range = [float(min(m.min() for m, _, _ in mfccs.values())), float(max(m.max() for m, _, _ in mfccs.values()))]
        if color_range[0] == color_range[1]:
            color_range[1] = color_range[0] + 1.0
        for tid, (m, times, title) in mfccs.items():
            artifacts.append((tid, "mfcc", render.mfcc_png(m, times, time_range, color_range, title)))

    done = [t for t in result_tracks if t["analysis_status"] == "completed"]
    if not done:
        status = "failed"
    elif source_errors or len(done) != len(result_tracks):
        status = "partial"
    else:
        status = "completed"
    ok_devices = {t["device_id"] for t in done} - {t["device_id"] for t in result_tracks if t["analysis_status"] != "completed"}
    result = {
        "session_id": str(session_id), "run_id": str(run_id), "status": status,
        "analysis_sample_rate": sc.ANALYSIS_SAMPLE_RATE,
        "completed_device_count": len(ok_devices), "analyzable_track_count": len(done),
        "duration_seconds": (time_range[1] - time_range[0]) if time_range else 0.0,
        "time_range": time_range, "mfcc_color_range": color_range,
        "spectrogram_color_range": list(sc.SPECTROGRAM_DB_RANGE),
        "parameters": sc.PARAMETERS,
        "versions": {"analysis_service": f"{pub.PRODUCER}/{sc.ALGORITHM_VERSION}", "producer": pub.PRODUCER},
        "source_errors": source_errors, "tracks": result_tracks}

    summary = {"session_id": str(session_id), "run_id": str(run_id), "status": status, "skipped": False,
               "tracks_completed": len(done), "tracks_total": len(result_tracks), "source_errors": len(source_errors),
               "artifacts": len(artifacts), "fingerprint": fingerprint}
    if dry_run is not None:
        out = Path(dry_run)
        out.mkdir(parents=True, exist_ok=True)
        (out / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        for tid, kind, content in artifacts:
            (out / f"{tid}_{kind}.{'npz' if kind == 'matrices' else 'png'}").write_bytes(content)
        summary["dry_run"] = str(out)
        return summary
    written = pub.publish(conn, session_id=session_id, run_id=run_id, fingerprint=fingerprint, start_seconds=start_seconds,
                          end_seconds=end_seconds, status=status, result=result, tracks=track_rows, artifacts=artifacts,
                          force=force)
    if not written:
        # 另一個 worker 在這次計算期間已經替同一批輸入發布了結果；保留它，這次的內容沒有寫入
        kept = pub.existing_run(conn, session_id, fingerprint)
        conn.rollback()
        summary.update({"status": kept["status"] if kept else status, "skipped": True, "kept_existing": True,
                        "this_attempt_status": status})
    return summary


CANDIDATES_SQL = """
SELECT s.id
FROM mobile_capture.recording_sessions s
WHERE s.status IN ('completed', 'interrupted')
  AND EXISTS (SELECT 1 FROM mobile_capture.audio_assets a WHERE a.session_id = s.id)
ORDER BY s.created_at
"""


def pending_sessions(conn):
    """已結束、至少有一個封存音檔，而且「目前這批來源」還沒有外部整段結果的 session。
    用 fingerprint 判斷：晚到的裝置補封存後來源集合改變，fingerprint 跟著變，會再排一次完整分析（規格 7.7）；
    同一批來源已經有結果（即使是 partial／failed）就不自動重跑，要重跑請用 --session。"""
    with conn.cursor() as cur:
        cur.execute(CANDIDATES_SQL)
        ids = [r["id"] for r in cur.fetchall()]
    out = []
    for sid in ids:
        rows = src.list_sources(conn, sid)
        if rows and pub.existing_run(conn, sid, session_fingerprint(rows, 0.0, None)) is None:
            out.append(sid)
    conn.rollback()
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="地端外部分析：每聲道 Spectrogram／MFCC，寫回共用資料庫")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--session", help="要分析的 session_id")
    g.add_argument("--pending", action="store_true", help="處理所有還沒有外部整段結果的 session")
    ap.add_argument("--start", type=float, default=0.0, help="區間起點（秒）")
    ap.add_argument("--end", type=float, default=None, help="區間終點（秒）；省略＝到結尾")
    ap.add_argument("--matrices", choices=("auto", "always", "never"), default="auto",
                    help="數值矩陣（NPZ）是否寫進資料庫；auto＝壓縮後 64 MB 以內才寫")
    ap.add_argument("--force", action="store_true",
                    help="同一批輸入已有結果時仍重算，並取代那一筆。不加這個參數時，已有結果（不論狀態）一律保留、不覆寫")
    ap.add_argument("--dry-run", default=None, help="不寫資料庫，把 result.json 與圖存到這個資料夾")
    ap.add_argument("--once", action="store_true", help="--pending 時處理完目前的清單就結束")
    ap.add_argument("--poll-seconds", type=float, default=30.0)
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    url = os.environ.get("TRACK_ANALYSIS_DATABASE_URL")
    if not url:
        raise SystemExit("請設定環境變數 TRACK_ANALYSIS_DATABASE_URL")
    if args.session:
        try:
            sid = uuid.UUID(args.session)
        except ValueError:
            raise SystemExit("--session 必須是 UUID")
        with connect(url) as conn:
            try:
                s = analyse_session(conn, sid, args.start, args.end, args.matrices, args.force, args.dry_run)
            except (LookupError, ValueError) as e:
                raise SystemExit(str(e))
        print(json.dumps(s, ensure_ascii=False, indent=1))
        return s
    if args.dry_run or args.start != 0.0 or args.end is not None:
        raise SystemExit("--pending 只做整段分析並寫回；--dry-run、--start、--end 請搭配 --session")
    gave_up = set()                          # 這次執行中分析時出錯的 session：不在同一次執行裡反覆重試
    while True:
        with connect(url) as conn:
            for sid in pending_sessions(conn):
                if sid in gave_up:
                    continue
                try:
                    s = analyse_session(conn, sid, 0.0, None, args.matrices)
                    log.info("session %s → %s（完成 %s/%s 軌，來源錯誤 %s）", sid, s["status"],
                             s.get("tracks_completed"), s.get("tracks_total"), s.get("source_errors"))
                except Exception:  # noqa: BLE001
                    conn.rollback()
                    gave_up.add(sid)
                    log.exception("session %s 分析失敗；這次執行不再重試，請用 --session 個別處理", sid)
        if args.once:
            return None
        time.sleep(args.poll_seconds)


if __name__ == "__main__":
    main()
