"""讀取輸入：來源清單、從資料庫重建原始檔並驗證、解碼成各聲道（規格第 4 節）。

只做 SELECT。原始錄音表（audio_assets、audio_chunks、participant_recordings…）不改、不刪。
"""
import hashlib
import shutil
import subprocess

import numpy as np
import soundfile as sf

SUPPORTED_RATES = (44100, 48000)

# 規格 4.1。LEFT JOIN 保留尚未封存或缺失的裝置，讓分析回報缺失而不是悄悄省略。
SOURCES_SQL = """
SELECT s.id AS session_id, s.status AS session_status,
       s.created_at, s.conditions, r.code AS room_code,
       pr.participant_id, pr.source_position,
       p.name AS device_name, pr.status AS recording_status,
       pr.interrupted, pr.requested_sample_rate,
       pr.requested_channel_count,
       pr.sample_rate AS reported_sample_rate,
       pr.channel_count AS reported_channel_count,
       pr.duration_ms, pr.expected_chunks,
       a.mime_type, a.chunk_count, a.byte_count, a.checksum
FROM mobile_capture.recording_sessions s
JOIN mobile_capture.recording_rooms r ON r.id = s.room_id
JOIN mobile_capture.participant_recordings pr ON pr.session_id = s.id
JOIN mobile_capture.room_participants p ON p.id = pr.participant_id
LEFT JOIN mobile_capture.audio_assets a
  ON a.session_id = pr.session_id AND a.participant_id = pr.participant_id
WHERE s.id = %s
ORDER BY pr.source_position, pr.participant_id
"""

# 規格 4.2
CHUNKS_SQL = """
SELECT chunk_index, audio_data, checksum
FROM mobile_capture.audio_chunks
WHERE session_id = %s AND participant_id = %s
ORDER BY chunk_index
"""


class SourceError(Exception):
    """某一個來源無法使用。訊息會寫進 result.source_errors 給網頁看，所以不含地端路徑。"""


def list_sources(conn, session_id):
    with conn.cursor() as cur:
        cur.execute(SOURCES_SQL, (session_id,))
        return cur.fetchall()


def rebuild_asset(conn, session_id, participant_id, asset, dest):
    """依 chunk_index 串接原始位元組寫到 dest（串流，不整檔放記憶體），並驗證：
    索引從 0 連續、每段 SHA-256、分段數、總位元組數、整檔 SHA-256 等於 audio_assets.checksum。"""
    whole = hashlib.sha256()
    count = total = 0
    with conn.cursor(name=f"chunks_{participant_id.hex}") as cur, open(dest, "wb") as fh:
        cur.itersize = 4                       # 單段最大 8 MB；一次只取幾段
        cur.execute(CHUNKS_SQL, (session_id, participant_id))
        for row in cur:
            data = bytes(row["audio_data"])
            if row["chunk_index"] != count:
                raise SourceError(f"音段索引不連續：預期第 {count} 段，實際第 {row['chunk_index']} 段")
            if not row["checksum"]:
                raise SourceError(f"第 {count} 段沒有 SHA-256 紀錄，無法驗證")
            if hashlib.sha256(data).hexdigest() != row["checksum"]:
                raise SourceError(f"第 {count} 段的 SHA-256 與紀錄不符")
            whole.update(data)
            fh.write(data)
            count += 1
            total += len(data)
    if count == 0:
        raise SourceError("找不到任何音段")
    if count != asset["chunk_count"]:
        raise SourceError(f"音段數 {count} 與封存紀錄 {asset['chunk_count']} 不符")
    if total != asset["byte_count"]:
        raise SourceError(f"位元組數 {total} 與封存紀錄 {asset['byte_count']} 不符")
    if whole.hexdigest() != asset["checksum"]:
        raise SourceError("整檔 SHA-256 與封存紀錄不符")


def ffmpeg_exe():
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as e:  # noqa: BLE001
        raise SourceError("地端沒有 ffmpeg，無法解碼") from e


DECODE_TIMEOUT_S = 1800


def decode_to_wav(src, wav):
    """解碼成 wav 檔，不改取樣率與聲道數。回傳 (sample_rate, channels, frames)，不把音訊讀進記憶體。
    取樣率、聲道數、frames 一律以這裡解碼出來的為準，不採用檔名或回報的 metadata（規格 4.2、5.1）。
    逾時、解碼程式起不來、檔案壞掉，都轉成 SourceError：一個來源的問題不該讓整個 session 的其他來源也發布不了。"""
    cmd = [ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y", "-i", str(src), "-vn", "-c:a", "pcm_f32le", str(wav)]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=DECODE_TIMEOUT_S)
    except subprocess.TimeoutExpired as e:
        raise SourceError(f"原始檔解碼超過 {DECODE_TIMEOUT_S} 秒上限") from e
    except OSError as e:
        raise SourceError("地端的解碼程式無法啟動") from e
    if p.returncode != 0:
        raise SourceError("原始檔無法解碼")
    try:
        info = sf.info(str(wav))
    except Exception as e:  # noqa: BLE001
        raise SourceError("原始檔無法解碼") from e
    if info.frames == 0:
        raise SourceError("解碼後沒有任何音訊")
    if info.channels not in (1, 2):
        raise SourceError(f"解碼後是 {info.channels} 聲道；只支援 Mono 與 Stereo")
    if info.samplerate not in SUPPORTED_RATES:
        raise SourceError(f"解碼後取樣率 {info.samplerate} Hz；只支援 44100 與 48000 Hz")
    return int(info.samplerate), int(info.channels), int(info.frames)


def read_wav(wav):
    """把 decode_to_wav 產生的檔案讀成 float64，形狀 (frames, channels)。一次只讀一台裝置。"""
    try:
        data, _ = sf.read(str(wav), dtype="float64", always_2d=True)
    except Exception as e:  # noqa: BLE001
        raise SourceError("原始檔無法解碼") from e
    if not np.all(np.isfinite(data)):
        raise SourceError("解碼後含有無效數值")
    return data


def analysis_length(frames, sample_rate):
    """重取樣到 44100 Hz 之後的樣本數（和 scipy.signal.resample_poly 的輸出長度一致），不必真的重取樣就能算出時間軸。"""
    if sample_rate == 44100:
        return int(frames)
    if sample_rate == 48000:
        return -(-int(frames) * 147 // 160)
    raise SourceError(f"解碼後取樣率 {sample_rate} Hz；只支援 44100 與 48000 Hz")
