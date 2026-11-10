"""sync_chirp.py — 三手機同步嗶聲的共用規格與偵測。

前端 frontend/src/syncChirp.ts 必須使用同一組參數（CHIRP_* 常數）。改一邊就要改另一邊，
並重跑 analysis/tests/test_synthetic.py 與 frontend/tests-unit/syncChirp.test.ts。

嗶聲：線性掃頻 1500 → 7500 Hz、長 0.5 s、頭尾各 10 ms 餘弦漸變。
時間頻寬積 3000，匹配濾波在寬頻機台噪音下仍有約 35 dB 處理增益。
主控手機在錄音開始與結束各播一次：開頭那聲給偏移，兩聲之間給時脈漂移。
注意：偵測到的到達時間包含「主控手機到各麥克風的傳播時間」（每公尺約 2.9 ms），
不是純粹的錄音啟動時間差；精對齊再交給機台聲的 GCC-PHAT。
"""
import numpy as np
import scipy.signal as ss

CHIRP_F0_HZ = 1500.0
CHIRP_F1_HZ = 7500.0
CHIRP_DURATION_S = 0.5
CHIRP_FADE_S = 0.010
CHIRP_AMPLITUDE = 0.8


def chirp_template(sr):
    """與前端相同的嗶聲波形（float64，長度 round(sr * CHIRP_DURATION_S)）。"""
    n = int(round(sr * CHIRP_DURATION_S))
    t = np.arange(n) / sr
    k = (CHIRP_F1_HZ - CHIRP_F0_HZ) / CHIRP_DURATION_S
    y = CHIRP_AMPLITUDE * np.sin(2 * np.pi * (CHIRP_F0_HZ * t + 0.5 * k * t * t))
    nf = int(round(sr * CHIRP_FADE_S))
    if nf > 0:
        ramp = 0.5 - 0.5 * np.cos(np.pi * np.arange(nf) / nf)
        y[:nf] *= ramp
        y[-nf:] *= ramp[::-1]
    return y


def detect_chirps(x, sr, min_score=12.0, min_updown=3.0, min_gap_s=1.0, max_count=4):
    """在單聲道訊號 x 中找嗶聲起點。

    回傳 [(start_s, score), ...]，依時間排序。兩個條件都要過：
    1. score＝上掃匹配濾波包絡峰值的 robust z 分數 >= min_score；
    2. 上掃／下掃比 >= min_updown：同一位置附近，上掃濾波峰值 ÷ 下掃（時間反轉）濾波峰值。
       兩個濾波器頻譜大小相同，機台的穩態諧波與寬頻噪音對兩者反應相當；只有真正的上掃嗶聲
       會在上掃濾波器壓縮成尖峰。2026-11-10 在無嗶聲的真實錄音上，只用條件 1 會誤報 4 個。
    """
    tpl = chirp_template(sr)
    if len(x) < 2 * len(tpl):
        return []
    sos = ss.butter(4, [CHIRP_F0_HZ * 0.8, min(CHIRP_F1_HZ * 1.2, 0.45 * sr)], btype="band", fs=sr, output="sos")
    xf = ss.sosfiltfilt(sos, x)
    up = np.abs(ss.hilbert(ss.fftconvolve(xf, tpl[::-1], mode="valid")))    # up[k]：嗶聲從 x[k] 開始
    down = np.abs(ss.hilbert(ss.fftconvolve(xf, tpl, mode="valid")))        # 對照：下掃
    med = np.median(up)
    mad = np.median(np.abs(up - med)) + 1e-20
    score = (up - med) / (1.4826 * mad)
    half = len(tpl) // 2
    out = []
    gap = int(min_gap_s * sr)
    work = score.copy()
    for _ in range(4 * max_count):
        if len(out) >= max_count:
            break
        k = int(np.argmax(work))
        if work[k] < min_score:
            break
        ratio = up[k] / (down[max(0, k - half):k + half].max() + 1e-20)
        if ratio >= min_updown:
            out.append((k / sr, float(score[k])))
            work[max(0, k - gap):k + gap] = -np.inf
        else:
            work[max(0, k - half):k + half] = -np.inf
    return sorted(out)
