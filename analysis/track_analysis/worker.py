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
import importlib.metadata
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


def display_name(row):
    """顯示名稱，格式和網站內建分析一致：「錄音位置 · 錄音者名稱」，例如「A · 錄音者 A」。"""
    if row["source_position"]:
        return f"{row['source_position']} · {row['participant_name']}"
    return row["participant_name"]


def versions():
    out = {"analysis_service": f"{pub.PRODUCER}/{sc.ALGORITHM_VERSION}", "producer": pub.PRODUCER}
    for name in ("numpy", "scipy", "matplotlib", "soundfile"):
        try:
            out[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            pass
    return out


def session_fingerprint(rows, start_seconds, end_seconds):
    return pub.make_fingerprint([(r["participant_id"], r["checksum"]) for r in rows],
                                start_seconds, end_seconds, sc.PARAMETERS)


def prepare_sources(conn, session_id, rows, work):
    """重建、驗證、解碼成暫存 wav。回傳 (devices, source_errors)。
    devices 只帶檔案路徑與格式資訊，不帶音訊；音訊之後一次只讀一台裝置，記憶體用量不隨裝置數增加。
    失敗或缺失的來源寫進 source_errors（規格 6.4），不影響其他來源。"""
    devices, errors = [], []
    for r in rows:
        ident = {"device_id": str(r["participant_id"]), "device_name": display_name(r)}
        if r["checksum"] is None:
            errors.append({**ident, "status": "missing", "error": "這台裝置的音檔尚未封存"})
            continue
        raw = work / f"{r['participant_id']}.bin"
        wav = work / f"{r['participant_id']}.wav"
        try:
            src.rebuild_asset(conn, session_id, r["participant_id"], r, raw)
            sr, channels, frames = src.decode_to_wav(raw, wav)
        except src.SourceError as e:
            errors.append({**ident, "status": "failed", "error": str(e)})
            wav.unlink(missing_ok=True)
            continue
        finally:
            conn.rollback()                      # 結束讀取用的交易，不佔著連線
            raw.unlink(missing_ok=True)
        devices.append({"row": r, "wav": wav, "sample_rate": sr, "channels": channels, "frames": frames})
    return devices, errors


class _Unreadable(Exception):
    def __init__(self, device, error):
        super().__init__(error["error"])
        self.device, self.error = device, error


def analyse_devices(devices, session_id, run_id, known_ids, start_seconds, end_seconds, time_range, matrices):
    """逐台裝置、逐聲道計算並出圖。回傳 (artifacts, result.tracks 的內容, MFCC 色階)。

    一個聲道算不出來或圖畫不出來，只把那個聲道標成 failed，其他聲道照常（和網站內建分析相同）。
    一次只把一台裝置的音訊讀進記憶體。"""
    artifacts, entries, mfccs = [], [], {}
    for d in devices:
        r, sr = d["row"], d["sample_rate"]
        pid, name = r["participant_id"], display_name(r)
        try:
            data = src.read_wav(d["wav"])
        except src.SourceError as e:
            raise _Unreadable(d, {"device_id": str(pid), "device_name": name, "status": "failed", "error": str(e)}) from e
        for idx, label in enumerate(CHANNEL_LABELS[data.shape[1]]):
            tid = known_ids.get((pid, idx)) or pub.track_uuid(session_id, pid, idx)
            entry = {
                "track_id": str(tid), "session_id": str(session_id), "device_id": str(pid),
                "device_name": name, "channel_index": idx, "channel_label": label,
                "source_channel_count": data.shape[1],
                "requested_sample_rate": r["requested_sample_rate"], "reported_sample_rate": r["reported_sample_rate"],
                "original_sample_rate": sr, "actual_sample_rate": sr,
                "analysis_sample_rate": sc.ANALYSIS_SAMPLE_RATE, "duration_seconds": data.shape[0] / sr,
                "total_frames": int(data.shape[0]), "audio_asset_id": f"{session_id}/{pid}",
                "source_checksum": r["checksum"], "interrupted": bool(r["interrupted"]),
                "analysis_status": "no_data", "spectrogram_url": None, "mfcc_url": None}
            entries.append(entry)
            try:
                a = sc.analyze_channel(np.ascontiguousarray(data[:, idx]), sr, start_seconds, end_seconds)
            except sc.NoData:
                entry["error"] = "選取區間沒有足夠的有效樣本（至少 2048 samples）"
                continue
            except Exception:  # noqa: BLE001
                log.exception("聲道分析失敗：%s", tid)
                entry.update({"analysis_status": "failed", "error": "此聲道分析失敗"})
                continue
            title = f"{name}｜{label}"
            try:
                mine, stored = [(tid, "spectrogram", render.spectrogram_png(a["spectrogram_db"], a["times"], time_range, title))], False
                if matrices == "always" or (matrices == "auto" and a["spectrogram_db"].nbytes <= 8 * MATRICES_AUTO_LIMIT):
                    npz = render.matrices_npz(a["spectrogram_db"], a["mfcc"], a["times"], a["valid_range"])
                    if matrices == "always" or len(npz) <= MATRICES_AUTO_LIMIT:
                        mine.append((tid, "matrices", npz))
                        stored = True
                    del npz
            except Exception:  # noqa: BLE001
                log.exception("圖表產生失敗：%s", tid)
                entry.update({"analysis_status": "failed", "error": "圖表產生失敗"})
                continue
            artifacts.extend(mine)
            entry["matrices_stored"] = stored
            if not stored and matrices == "auto":
                entry["matrices_note"] = "矩陣超過自動上限，未寫入資料庫"
            mfccs[tid] = (a["mfcc"], a["times"], title, entry)
            entry.update({"analysis_status": "completed", "valid_range": [float(v) for v in a["valid_range"]],
                          "spectrogram_url": pub.artifact_url(session_id, run_id, tid, "spectrogram"),
                          "mfcc_url": pub.artifact_url(session_id, run_id, tid, "mfcc")})
            del a
        del data

    # MFCC 色階：同一 run 所有成功音軌共用 min/max，不逐張正規化（規格第 8 節）。
    # 沒有任何成功音軌時的預設值 [-1, 1] 和網站內建分析相同。
    color_range = [float(min((m.min() for m, _, _, _ in mfccs.values()), default=-1.0)),
                   float(max((m.max() for m, _, _, _ in mfccs.values()), default=1.0))]
    if color_range[0] == color_range[1]:
        color_range[1] += 1.0
    for tid, (m, times, title, entry) in mfccs.items():
        try:
            png = render.mfcc_png(m, times, time_range, color_range, title)
        except Exception:  # noqa: BLE001
            log.exception("圖表產生失敗：%s", tid)
            artifacts[:] = [x for x in artifacts if x[0] != tid]          # 這個聲道已經做好的圖和矩陣也一起撤掉
            entry.update({"analysis_status": "failed", "error": "圖表產生失敗", "spectrogram_url": None, "mfcc_url": None,
                          "matrices_stored": False})
            entry.pop("matrices_note", None)
            continue
        artifacts.append((tid, "mfcc", png))
    return artifacts, entries, color_range


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
        while True:
            # 整批共用的時間軸（規格第 8 節），定義和網站內建分析相同：有指定終點就用它，否則到最長那一軌的結尾。
            # 由各檔案的長度算出，不必先把音訊讀進來。
            longest = max((d["frames"] / d["sample_rate"] for d in devices), default=None)
            time_range = [start_seconds, float(end_seconds if end_seconds is not None
                                               else (longest if longest is not None else start_seconds + 1.0))]
            time_range[1] = max(time_range[1], time_range[0] + 0.01)
            try:
                artifacts, result_tracks, color_range = analyse_devices(
                    devices, session_id, run_id, known_ids, start_seconds, end_seconds, time_range, matrices)
                break
            except _Unreadable as e:
                # 解碼成功的檔案後來讀不回來（很少見）：這台改列為來源失敗，其餘重算一次，
                # 讓共用時間軸只依實際有音軌的裝置決定（和內建分析相同）
                source_errors.append(e.error)
                devices = [d for d in devices if d is not e.device]

    track_rows = [{"track_id": uuid.UUID(t["track_id"]), "device_id": uuid.UUID(t["device_id"]),
                   **{k: t[k] for k in ("device_name", "channel_index", "channel_label", "source_channel_count",
                                        "requested_sample_rate", "original_sample_rate", "actual_sample_rate",
                                        "analysis_sample_rate", "duration_seconds", "total_frames", "analysis_status")}}
                  for t in result_tracks]

    done = [t for t in result_tracks if t["analysis_status"] == "completed"]
    if not done:
        status = "failed"
    elif source_errors or len(done) != len(result_tracks):
        status = "partial"
    else:
        status = "completed"
    # 下面四個欄位的算法和網站內建分析（backend/analysis.py）相同，前端不管讀到哪一邊的結果，意思都一樣
    result = {
        "session_id": str(session_id), "run_id": str(run_id), "status": status,
        "analysis_sample_rate": sc.ANALYSIS_SAMPLE_RATE,
        "completed_device_count": sum(1 for r in rows if r["checksum"]),      # 已完整封存的裝置數
        "analyzable_track_count": len(done),
        "duration_seconds": max((t["duration_seconds"] for t in result_tracks), default=0),   # 最長那一軌的原始時長
        "time_range": time_range, "mfcc_color_range": color_range,
        "spectrogram_color_range": list(sc.SPECTROGRAM_DB_RANGE),
        "parameters": sc.PARAMETERS,
        "versions": versions(),
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
