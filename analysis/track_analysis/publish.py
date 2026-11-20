"""寫回結果：recording_tracks、track_analysis_runs、track_analysis_artifacts（規格第 6、7 節）。

與網站內建 worker 的關係（規格 7.1）：內建 worker 會自動領取 queued 工作，網站重啟時還會把 running 改回 queued。
所以本程式**不建立 queued／running 的工作**：先在地端算完，再用一個交易把最終狀態（completed／partial／failed）、
result、tracks、artifacts 一次寫入。內建 worker 從頭到尾看不到可以領取的列。
fingerprint 一律以 "ext:mirdc-onprem:" 開頭，不會和內建分析的 fingerprint 相同。
"""
import hashlib
import json
import uuid

from psycopg.types.json import Jsonb

PRODUCER = "mirdc-onprem"
FINGERPRINT_PREFIX = f"ext:{PRODUCER}:"
FINAL_STATUSES = ("completed", "partial", "failed")
ARTIFACT_KINDS = ("spectrogram", "mfcc", "matrices")
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class PublishError(Exception):
    pass


def track_uuid(session_id, participant_id, channel_index):
    """規格第 3 節的 track_id 規則。"""
    return uuid.uuid5(uuid.NAMESPACE_URL, f"cnc:{session_id}:{participant_id}:{channel_index}")


def make_fingerprint(sources, start_seconds, end_seconds, parameters):
    """由來源 checksum、區間、演算法名稱／版本與參數決定（規格 6.2）。
    sources：[(device_id, checksum 或 None)]。來源集合改變（例如晚到的裝置補封存）就會得到新的 fingerprint。"""
    # + 0.0：把 -0.0 正規化成 0.0，同一個區間不會得到兩個 fingerprint
    body = {"producer": PRODUCER, "parameters": parameters,
            "start_seconds": float(start_seconds) + 0.0,
            "end_seconds": None if end_seconds is None else float(end_seconds) + 0.0,
            "sources": sorted([str(d), c] for d, c in sources)}
    digest = hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    return FINGERPRINT_PREFIX + digest.hexdigest()


def run_uuid(session_id, fingerprint):
    """同一批輸入重試會得到同一個 run_id，artifact 不會重複（規格 7.6）。"""
    return uuid.uuid5(uuid.NAMESPACE_URL, f"cnc-ext-run:{session_id}:{fingerprint}")


def existing_run(conn, session_id, fingerprint):
    with conn.cursor() as cur:
        cur.execute("SELECT id, status FROM mobile_capture.track_analysis_runs WHERE session_id=%s AND fingerprint=%s",
                    (session_id, fingerprint))
        return cur.fetchone()


def existing_track_ids(conn, session_id):
    with conn.cursor() as cur:
        cur.execute("SELECT device_id, channel_index, track_id FROM mobile_capture.recording_tracks WHERE session_id=%s",
                    (session_id,))
        return {(r["device_id"], r["channel_index"]): r["track_id"] for r in cur.fetchall()}


def artifact_url(session_id, run_id, track_id, kind):
    return f"/api/v1/sessions/{session_id}/analysis/{run_id}/tracks/{track_id}/{kind}.png"


TRACK_UPSERT = """
INSERT INTO mobile_capture.recording_tracks
 (track_id, session_id, device_id, device_name, channel_index, channel_label, source_channel_count,
  requested_sample_rate, original_sample_rate, actual_sample_rate, analysis_sample_rate,
  duration_seconds, total_frames, analysis_status)
VALUES (%(track_id)s, %(session_id)s, %(device_id)s, %(device_name)s, %(channel_index)s, %(channel_label)s,
        %(source_channel_count)s, %(requested_sample_rate)s, %(original_sample_rate)s, %(actual_sample_rate)s,
        %(analysis_sample_rate)s, %(duration_seconds)s, %(total_frames)s, %(analysis_status)s)
ON CONFLICT (session_id, device_id, channel_index) DO UPDATE SET
  device_name = EXCLUDED.device_name,
  analysis_status = CASE WHEN %(whole_recording)s THEN EXCLUDED.analysis_status
                         ELSE mobile_capture.recording_tracks.analysis_status END
RETURNING track_id
"""

# 同一批輸入（同一個 fingerprint）已經有結果時，不加 force 就一律不覆寫（使用者 2026-11-20 決定）。
# 先前試過「不比現有的差才覆寫」（比狀態、再比成功音軌數），三輪審查每次都找到漏掉的條件，
# 所以改成沒有比較邏輯的規則：先寫入的那一筆留著；要重算、要取代，只能明確加 --force。
# 唯一索引讓第二個交易等第一個提交後才判斷，所以兩個 worker 同時跑也只會有一筆寫入。
RUN_INSERT = """
INSERT INTO mobile_capture.track_analysis_runs (id, session_id, fingerprint, start_seconds, end_seconds, status, result)
VALUES (%(id)s, %(session_id)s, %(fingerprint)s, %(start)s, %(end)s, %(status)s, %(result)s)
ON CONFLICT (session_id, fingerprint) DO NOTHING
RETURNING id
"""

# force：只覆寫「同一個 id」的列，也就是這個外部系統自己先前為同一批輸入寫的那一筆；別人的列不動
RUN_FORCE_UPSERT = """
INSERT INTO mobile_capture.track_analysis_runs AS r (id, session_id, fingerprint, start_seconds, end_seconds, status, result)
VALUES (%(id)s, %(session_id)s, %(fingerprint)s, %(start)s, %(end)s, %(status)s, %(result)s)
ON CONFLICT (session_id, fingerprint) DO UPDATE SET status = EXCLUDED.status, result = EXCLUDED.result
  WHERE r.id = EXCLUDED.id
RETURNING id
"""

ARTIFACT_UPSERT = """
INSERT INTO mobile_capture.track_analysis_artifacts (run_id, track_id, kind, content)
VALUES (%s, %s, %s, %s)
ON CONFLICT (run_id, track_id, kind) DO UPDATE SET content = EXCLUDED.content
"""

# 規格 7.5：artifacts 的兩個外鍵不保證 track 與 run 屬於同一個 session，寫入者必須自己驗證
CROSS_SESSION_CHECK = """
SELECT count(*) AS n
FROM mobile_capture.track_analysis_artifacts a
JOIN mobile_capture.track_analysis_runs r ON r.id = a.run_id
JOIN mobile_capture.recording_tracks t ON t.track_id = a.track_id
WHERE a.run_id = %s AND (t.session_id <> r.session_id OR r.session_id <> %s)
"""


def publish(conn, *, session_id, run_id, fingerprint, start_seconds, end_seconds, status, result, tracks, artifacts,
            force=False):
    """一個交易寫入全部內容；任何一步失敗就整筆回復，資料庫裡不會留下半套結果。

    tracks：recording_tracks 的列（dict，含 track_id）。只放成功解碼的聲道。
    artifacts：[(track_id, kind, bytes)]。
    result：規格 6.4 的 JSON；裡面的 run_id、session_id、track_id、圖的 URL 必須和這裡寫入的列一致。
    回傳 True＝已寫入；False＝資料庫已有同一批輸入的結果而且沒有 force，這次的內容沒有寫入（什麼都沒改）。
    force=True 才會取代既有的那一筆（同一個 run_id）。
    """
    if conn.autocommit:
        raise PublishError("連線是 autocommit，無法保證整筆一起成功或一起回復；請用一般交易模式的連線")
    if status not in FINAL_STATUSES:
        raise PublishError(f"只能寫入最終狀態，不能寫入 {status!r}")
    if not fingerprint.startswith(FINGERPRINT_PREFIX):
        raise PublishError("fingerprint 必須屬於外部系統自己的命名空間")
    if result.get("run_id") != str(run_id) or result.get("session_id") != str(session_id) or result.get("status") != status:
        raise PublishError("result 內的 run_id／session_id／status 與要寫入的工作不一致")
    known = {t["track_id"] for t in tracks}
    if len(known) != len(tracks):
        raise PublishError("要寫入的音軌有重複的 track_id")
    listed = []
    for t in result.get("tracks", []):
        if t.get("session_id") != str(session_id) or uuid.UUID(t["track_id"]) not in known:
            raise PublishError("result.tracks 引用了不屬於這次寫入的音軌")
        listed.append(uuid.UUID(t["track_id"]))
    if len(set(listed)) != len(listed) or set(listed) != known:
        raise PublishError("要寫入的音軌與 result.tracks 不是同一組（有遺漏或重複）")
    by_id = {t["track_id"]: t for t in tracks}
    for t in result["tracks"]:
        if by_id[uuid.UUID(t["track_id"])]["analysis_status"] != t.get("analysis_status"):
            raise PublishError("音軌列的狀態與 result.tracks 的狀態不一致")
    done = sum(1 for t in result.get("tracks", []) if t.get("analysis_status") == "completed")
    if result.get("analyzable_track_count") != done:
        raise PublishError("result.analyzable_track_count 與成功音軌數不一致")
    if (status == "completed") != (done > 0 and done == len(listed) and not result.get("source_errors")) \
            or (status == "failed") != (done == 0):
        raise PublishError("狀態與內容不符：completed 必須全部成功且沒有來源錯誤；failed 必須沒有任何成功音軌")
    have = set()
    for track_id, kind, content in artifacts:
        if track_id not in known or kind not in ARTIFACT_KINDS or not content or (track_id, kind) in have:
            raise PublishError("artifact 引用了未知的音軌、種類，內容是空的，或重複")
        if kind in ("spectrogram", "mfcc") and not bytes(content).startswith(PNG_SIGNATURE):
            raise PublishError(f"{kind} 必須是 PNG 二進位內容")
        have.add((track_id, kind))
    # 結果裡每一個圖的 URL 都要有對應的 PNG；沒有成功的音軌不能有 URL 也不能有圖（規格 6.2、6.4）
    for t in result.get("tracks", []):
        tid = uuid.UUID(t["track_id"])
        for kind in ("spectrogram", "mfcc"):
            url = t.get(f"{kind}_url")
            if t.get("analysis_status") == "completed":
                if url != artifact_url(session_id, run_id, tid, kind) or (tid, kind) not in have:
                    raise PublishError(f"成功音軌的 {kind} URL 與實際寫入的 PNG 對不上")
            elif url is not None or (tid, kind) in have:
                raise PublishError("沒有成功的音軌不能有圖或圖的 URL")
        if t.get("analysis_status") != "completed" and any(a == tid for a, _ in have):
            raise PublishError("沒有成功的音軌不能有任何 artifact（含矩陣）")
    whole = float(start_seconds) == 0.0 and end_seconds is None
    conn.rollback()                              # 結束先前只用來讀取的交易，下面是一個全新的交易
    try:
        with conn.cursor() as cur:
            cur.execute(RUN_FORCE_UPSERT if force else RUN_INSERT,
                        {"id": run_id, "session_id": session_id, "fingerprint": fingerprint,
                         "start": float(start_seconds) + 0.0, "end": end_seconds, "status": status,
                         "result": Jsonb(result)})
            if cur.fetchone() is None:
                cur.execute("SELECT id FROM mobile_capture.track_analysis_runs WHERE session_id=%s AND fingerprint=%s",
                            (session_id, fingerprint))
                row = cur.fetchone()
                conn.rollback()
                if row and row["id"] == run_id and not force:
                    return False                 # 同一批輸入已經有結果：保留現有的，這次什麼都不寫
                raise PublishError("同一個 fingerprint 已經被另一筆工作使用，拒絕覆寫")
            for t in tracks:
                cur.execute(TRACK_UPSERT, {**t, "session_id": session_id, "whole_recording": whole})
                got = cur.fetchone()["track_id"]
                if got != t["track_id"]:
                    raise PublishError("資料庫既有的 track_id 與這次使用的不一致")
            for track_id, kind, content in artifacts:
                cur.execute(ARTIFACT_UPSERT, (run_id, track_id, kind, bytes(content)))
            cur.execute(CROSS_SESSION_CHECK, (run_id, session_id))
            if cur.fetchone()["n"] != 0:
                raise PublishError("artifact 的音軌與工作不屬於同一個 session")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return True
