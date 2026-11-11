"""地端分析 worker：從 mobile_capture.analysis_jobs 認領工作，下載三軌音段、解碼、跑 analyze_multi_mic，結果寫回資料表。

雲端後端只負責寫入；本程式在地端主動連出去，資料表是唯一溝通管道。
用法（連線字串放環境變數，不要寫進指令或程式）：
    $env:ANALYSIS_DATABASE_URL = 'postgresql://analysis_worker@<host>:5432/<db>?sslmode=require'
    python -X utf8 analysis/worker.py --work-dir D:/cnc_analysis            # 常駐
    python -X utf8 analysis/worker.py --work-dir D:/cnc_analysis --once     # 處理一筆就結束
設計說明見 docs/analysis-worker.md。
"""
import argparse
import hashlib
import json
import logging
import math
import re
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import traceback
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

PIPELINE_VERSION = "multi_mic-v1"
HERE = Path(__file__).resolve().parent
ANALYZER = HERE / "analyze_multi_mic.py"
LABELS = ("A", "B", "C")
log = logging.getLogger("analysis_worker")


class JobError(Exception):
    """可以顯示給網頁使用者的失敗原因（不含地端路徑或堆疊）。"""


def connect(url):
    c = psycopg.connect(url, row_factory=dict_row, connect_timeout=10)
    c.execute("SET search_path TO mobile_capture, public")
    # 資料庫等待有上限：鎖或查詢卡住時讓這次嘗試失敗，而不是讓工作永遠停在 running
    c.execute("SET statement_timeout = '120s'")
    c.execute("SET lock_timeout = '30s'")
    c.commit()
    return c


def code_commit():
    try:
        out = subprocess.run(["git", "-C", str(HERE), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=10)
        if out.returncode != 0:
            return None
        return out.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def ffmpeg_exe():
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as e:  # noqa: BLE001
        raise JobError("地端沒有 ffmpeg，無法解碼 webm") from e


# ---------- 工作佇列 ----------

def expire_exhausted(c):
    """租約過期且已用完重試次數的工作改為失敗，避免永遠停在 running。"""
    n = c.execute(
        "UPDATE analysis_jobs SET status='failed',finished_at=now(),worker_id=NULL,lease_expires_at=NULL,"
        "error=coalesce(error,'地端分析逾時或中斷，已達重試上限') "
        "WHERE status='running' AND lease_expires_at<now() AND attempts>=max_attempts").rowcount
    c.commit()
    return n


def claim(c, worker_id, lease_s, commit_id):
    """認領最舊的一筆可做工作。SKIP LOCKED 讓多台 worker 不會搶到同一筆。"""
    expire_exhausted(c)
    row = c.execute(
        """UPDATE analysis_jobs j SET status='running', worker_id=%(w)s,
               lease_expires_at=now()+%(lease)s*interval '1 second', attempts=attempts+1,
               started_at=now(), finished_at=NULL, pipeline_version=%(v)s, code_commit=%(cc)s
           WHERE j.id=(SELECT id FROM analysis_jobs
                       WHERE (status='queued' OR (status='running' AND lease_expires_at<now()))
                         AND attempts<max_attempts
                       ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1)
           RETURNING j.*""",
        {"w": worker_id, "lease": lease_s, "v": PIPELINE_VERSION, "cc": commit_id}).fetchone()
    c.commit()
    return row


# 所有權 = (id, worker_id, attempts) 且 status='running'。attempts 每次認領都加 1，
# 所以舊的嘗試（即使 worker_id 相同）在別人重新認領後，延長、失敗、完成都寫不進去。
# 租約過期只代表「可以被別人認領」；在被認領之前，原本的嘗試仍可完成。
OWNED = "id=%(id)s AND worker_id=%(w)s AND attempts=%(n)s AND status='running'"


def renew(url, job_id, worker_id, attempt, lease_s):
    with connect(url) as c:
        n = c.execute(
            "UPDATE analysis_jobs SET lease_expires_at=now()+%(lease)s*interval '1 second' WHERE " + OWNED,
            {"lease": lease_s, "id": job_id, "w": worker_id, "n": attempt}).rowcount
        c.commit()
    return n == 1


class Heartbeat(threading.Thread):
    """分析期間每 lease/3 秒延長租約；延長失敗代表工作已被別人接手。"""

    def __init__(self, url, job_id, worker_id, attempt, lease_s):
        super().__init__(daemon=True)
        self.args = (url, job_id, worker_id, attempt, lease_s)
        self.stop = threading.Event()
        self.lost = threading.Event()

    def run(self):
        while not self.stop.wait(max(1.0, self.args[4] / 3)):
            try:
                if not renew(*self.args):
                    self.lost.set()
                    return
            except psycopg.Error as e:
                log.warning("延長租約失敗（下次重試）：%s", e)


def fail(c, job, worker_id, message):
    # 重試與否用資料庫當下的 attempts／max_attempts 判斷，不用認領時的快取值
    c.execute(
        "UPDATE analysis_jobs SET status=CASE WHEN attempts<max_attempts THEN 'queued' ELSE 'failed' END, "
        "error=%(e)s, worker_id=NULL, lease_expires_at=NULL, "
        "finished_at=CASE WHEN attempts<max_attempts THEN NULL ELSE now() END WHERE " + OWNED,
        {"e": message[:500], "id": job["id"], "w": worker_id, "n": job["attempts"]})
    c.commit()


MAX_RESIDUAL_SAMPLES = 2.0
MAX_RESIDUAL_PPM = 5.0


def _finite(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def alignment_verdict(summary):
    """對齊後重量一次的殘差都夠小才算「已驗證」；否則數字不可當作同步結果使用。
    以實際送進分析的聲源為準：每一支非 A 聲源都必須有 <聲源>_vs_A 且殘差欄位是有限數字。"""
    channels = [k for k in (summary.get("channels") or []) if k in LABELS]
    sync = summary.get("sync") if isinstance(summary.get("sync"), dict) else {}
    reasons = {}
    if "A" not in channels or len(channels) < 2:
        reasons["channels"] = "缺少可對齊的聲源"
    for k in channels:
        if k == "A":
            continue
        pair = f"{k}_vs_A"
        info = sync.get(pair)
        after = info.get("after_alignment") if isinstance(info, dict) else None
        if not isinstance(after, dict) or "error" in after:
            reasons[pair] = "對齊後無法重新量測"
            continue
        off, ppm = after.get("fine_offset_samples"), after.get("drift_ppm")
        if not (_finite(off) and _finite(ppm)):
            reasons[pair] = "對齊後的殘差欄位缺漏或不是數字"
        elif abs(off) > MAX_RESIDUAL_SAMPLES:
            reasons[pair] = f"殘餘偏移 {off:.2f} 取樣點"
        elif abs(ppm) > MAX_RESIDUAL_PPM:
            reasons[pair] = f"殘餘漂移 {ppm:.1f} ppm"
    return {"verified": not reasons, "channels": channels, "failed_pairs": reasons,
            "criteria": {"max_residual_samples": MAX_RESIDUAL_SAMPLES, "max_residual_ppm": MAX_RESIDUAL_PPM}}


def complete(c, job, worker_id, summary):
    """在同一個交易裡確認這次嘗試仍擁有工作，再寫結果。已被重新認領就不寫。"""
    owned = c.execute("SELECT id FROM analysis_jobs WHERE " + OWNED + " FOR UPDATE",
                      {"id": job["id"], "w": worker_id, "n": job["attempts"]}).fetchone()
    if not owned:
        c.rollback()
        return False
    sync = summary.get("sync", {})
    verdict = alignment_verdict(summary)
    c.execute(
        "INSERT INTO audio_alignment_runs(id,session_id,status,method,offsets,evidence,job_id) "
        "VALUES(gen_random_uuid(),%s,%s,%s,%s,%s,%s)",
        (job["session_id"], "verified" if verdict["verified"] else "unverified",
         "chirp_or_envelope+gcc_phat_hann+drift_fit",
         Jsonb({k: {f: v.get(f) for f in ("fine_offset_samples", "fine_offset_ms", "drift_ppm", "drift_compensated")}
                for k, v in sync.items() if isinstance(v, dict)}),
         Jsonb({"sync": sync, "sync_chirps_detected_s": summary.get("sync_chirps_detected_s"),
                "verdict": verdict}), job["id"]))
    result = {"kind": job["kind"], "job_id": str(job["id"]), "pipeline_version": PIPELINE_VERSION,
              "alignment": verdict,
              "code_commit": job.get("code_commit"), "attempt": job["attempts"], "summary": summary}
    c.execute("INSERT INTO analysis_results(id,session_id,result,job_id) VALUES(gen_random_uuid(),%s,%s,%s)",
              (job["session_id"], Jsonb(result), job["id"]))
    c.execute("UPDATE analysis_jobs SET status='completed', finished_at=now(), error=NULL, lease_expires_at=NULL "
              "WHERE id=%s", (job["id"],))
    c.commit()
    return True


# ---------- 下載與解碼 ----------

def fetch_tracks(c, session_id, dest):
    """依 audio_assets 校驗每段 SHA256、段數與整檔 SHA256，寫出 <聲源>.webm。"""
    rows = c.execute(
        "SELECT p.source_label, a.participant_id, a.chunk_count, a.checksum, a.mime_type "
        "FROM audio_assets a JOIN room_participants p ON p.id=a.participant_id "
        "JOIN participant_recordings pr ON pr.session_id=a.session_id AND pr.participant_id=a.participant_id "
        "WHERE a.session_id=%s AND pr.status='stored' ORDER BY p.source_label", (session_id,)).fetchall()
    c.commit()
    labels = [r["source_label"] for r in rows]
    if "A" not in labels or "B" not in labels:
        raise JobError(f"已封存音檔不足：至少需要 A 與 B，目前 {labels or '無'}")
    paths = {}
    for r in rows:
        whole, n = hashlib.sha256(), 0
        out = dest / f"{r['source_label']}.webm"
        with open(out, "wb") as fh, c.cursor(name="fetch_chunks") as cur:
            cur.execute("SELECT chunk_index, checksum, audio_data FROM audio_chunks "
                        "WHERE session_id=%s AND participant_id=%s ORDER BY chunk_index", (session_id, r["participant_id"]))
            for ch in cur:
                data = bytes(ch["audio_data"])
                if ch["chunk_index"] != n:
                    raise JobError(f"聲源 {r['source_label']} 缺少第 {n} 段")
                if hashlib.sha256(data).hexdigest() != ch["checksum"]:
                    raise JobError(f"聲源 {r['source_label']} 第 {n} 段 SHA256 不符")
                whole.update(data)
                fh.write(data)
                n += 1
        c.commit()
        if n != r["chunk_count"] or whole.hexdigest() != r["checksum"]:
            raise JobError(f"聲源 {r['source_label']} 段數或整檔 SHA256 與封存紀錄不符")
        paths[r["source_label"]] = out
    return paths


def decode(webm, wav, sr=48000):
    cmd = [ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y", "-i", str(webm),
           "-ac", "1", "-ar", str(sr), "-c:a", "pcm_f32le", str(wav)]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if p.returncode != 0 or not wav.exists():
        log.error("ffmpeg 失敗：%s", p.stderr[-2000:])
        raise JobError(f"{webm.stem} 解碼失敗")


_PATHISH = re.compile(r"[A-Za-z]:[\\/]|[\\/]")
_EXC_LINE = re.compile(r"^([A-Za-z_][\w.]*(?:Error|Exception|Exit))(?::\s*(.*))?$")


def public_error(stderr):
    """只回報例外類型與訊息，並遮掉任何像路徑的字串；完整 stderr 只留在地端 log。"""
    last = (stderr.strip().splitlines() or [""])[-1].strip()
    m = _EXC_LINE.match(last)
    if not m:
        return "分析程式失敗（詳見地端 log）"
    name, msg = m.group(1).split(".")[-1], (m.group(2) or "").strip()
    if _PATHISH.search(msg):
        # 路徑可能含空白，部分遮罩仍會漏字；有任何像路徑的內容就整段不回報
        return f"分析程式失敗（{name}，詳見地端 log）"
    return f"分析程式失敗（{name}）" + (f"：{msg[:200]}" if msg else "")


class LeaseLost(Exception):
    """這次嘗試已不再擁有工作（別人重新認領）。"""


def analyse(wavs, out, note, timeout_s, cancel=None, analyzer=None):
    """另開程序跑模型：記憶體在程序結束時釋放，模型崩潰也不會帶走 worker。
    cancel（threading.Event）被設定時立刻終止子程序，避免失去租約後還在佔用資源。"""
    out.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, "-X", "utf8", str(analyzer or ANALYZER), "--a", str(wavs["A"]), "--b", str(wavs["B"]),
           "--out", str(out), "--source-note", note]
    if "C" in wavs:
        cmd += ["--c", str(wavs["C"])]
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "MPLBACKEND": "Agg"}
    logf = out / "analyzer.log"
    with open(logf, "w", encoding="utf-8") as fh:
        p = subprocess.Popen(cmd, stdout=fh, stderr=subprocess.STDOUT, env=env)
        deadline = time.monotonic() + timeout_s
        while p.poll() is None:
            if cancel is not None and cancel.is_set():
                p.kill()
                p.wait()
                raise LeaseLost()
            if time.monotonic() > deadline:
                p.kill()
                p.wait()
                raise JobError(f"分析超過 {timeout_s} 秒上限")
            time.sleep(0.5)
    if p.returncode != 0:
        text = logf.read_text(encoding="utf-8", errors="replace")
        log.error("分析程式失敗：%s", text[-3000:])
        raise JobError(public_error(text))
    with open(out / "summary.json", encoding="utf-8") as fh:
        return json.load(fh)


# ---------- 主流程 ----------

def process(url, job, worker_id, work_dir, lease_s, timeout_s):
    # 每次嘗試各自一個資料夾：租約重疊時兩個嘗試不會互相覆寫音檔與輸出
    local = Path(work_dir) / str(job["session_id"]) / str(job["id"]) / f"attempt-{job['attempts']}"
    local.mkdir(parents=True, exist_ok=True)
    hb = Heartbeat(url, job["id"], worker_id, job["attempts"], lease_s)
    hb.start()
    try:
        with connect(url) as c:
            webms = fetch_tracks(c, job["session_id"], local)
        wavs = {}
        for k, w in webms.items():
            if hb.lost.is_set():
                raise LeaseLost()
            wavs[k] = local / f"{k}.wav"
            decode(w, wavs[k])
        summary = analyse(wavs, local / "out", f"session {job['session_id']} job {job['id']}", timeout_s, hb.lost)
    finally:
        hb.stop.set()
        hb.join(timeout=5)
    if hb.lost.is_set():
        raise LeaseLost()
    with connect(url) as c:
        ok = complete(c, job, worker_id, summary)
    log.info("工作 %s %s；地端輸出 %s", job["id"], "完成" if ok else "已被重新認領，未寫入", local)
    return ok


def run_once(url, worker_id, work_dir, lease_s, timeout_s, commit_id):
    with connect(url) as c:
        job = claim(c, worker_id, lease_s, commit_id)
    if not job:
        return None
    log.info("認領工作 %s（session %s，第 %d 次）", job["id"], job["session_id"], job["attempts"])
    try:
        return process(url, job, worker_id, work_dir, lease_s, timeout_s)
    except LeaseLost:
        log.warning("工作 %s 已被重新認領，停止本次嘗試且不寫入", job["id"])
        return False
    except JobError as e:
        message = str(e)
    except Exception:  # noqa: BLE001
        log.error("未預期錯誤：\n%s", traceback.format_exc())
        message = "地端分析程式錯誤（詳見地端 log）"
    log.warning("工作 %s 失敗：%s", job["id"], message)
    with connect(url) as c:
        fail(c, job, worker_id, message)
    return False


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--work-dir", required=True, help="地端輸出資料夾（音檔、圖、summary）")
    ap.add_argument("--once", action="store_true", help="最多處理一筆就結束")
    ap.add_argument("--poll-seconds", type=float, default=10.0)
    ap.add_argument("--lease-seconds", type=int, default=300)
    ap.add_argument("--timeout-seconds", type=int, default=3600)
    ap.add_argument("--worker-id", default=f"{socket.gethostname()}-{os.getpid()}")
    args = ap.parse_args(argv)
    url = os.environ.get("ANALYSIS_DATABASE_URL")
    if not url:
        ap.error("請設定環境變數 ANALYSIS_DATABASE_URL（不要把密碼寫在指令列）")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    commit_id = code_commit()
    log.info("worker %s 啟動，pipeline %s，commit %s", args.worker_id, PIPELINE_VERSION, commit_id)
    while True:
        try:
            got = run_once(url, args.worker_id, args.work_dir, args.lease_seconds, args.timeout_seconds, commit_id)
        except psycopg.OperationalError as e:
            log.warning("資料庫連不上，%s 秒後重試：%s", args.poll_seconds, e)
            got = None
        if args.once:
            return 0 if got is not False else 1
        if got is None:
            time.sleep(args.poll_seconds)


if __name__ == "__main__":
    sys.exit(main())
