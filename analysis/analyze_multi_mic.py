#!/usr/bin/env python
"""analyze_multi_mic.py — 2 或 3 支麥克風（各自獨立錄音檔 A/B/C）的同步、聲道間相位、背景雜音移除。

由本機 harness 的 analyze_two_mic.py（2026-11-10）推廣為 N=2..3，並做兩項修正：
- GCC-PHAT 前加 Hann 窗：原版矩形切窗會在「窗內延遲 0」產生假峰，把精對齊鎖在粗對齊值上。
- 時脈漂移補償：不同手機的取樣時脈差約 20 ppm，原版只做固定偏移。
未加這兩項時，新程式在真實兩手機錄音上與原版 11 項數字逐位相同（特徵化比對紀錄見 docs/updates/）。

步驟
1. 同步（B、C 各自對齊到 A）
   a. 粗對齊：先找同步嗶聲（sync_chirp.py，主控手機播放）；兩軌嗶聲數量與間隔一致 → 用嗶聲到達時間差。
      否則 → 1 kHz 對數能量包絡互相關（±3 s）。
   b. 精對齊：2 s Hann 窗 GCC-PHAT（±25 ms，略過含嗶聲的窗），峰值清楚（PHAT 分數 >= 20）的窗
      取中位數＝偏移，直線擬合＝漂移 ppm。
   c. 對齊：漂移 >= 0.5 ppm 且清楚窗 >= 5 → 依擬合直線平移＋重取樣；否則整數加分數取樣平移。
      對齊後再量一次偏移與漂移（summary.json 的 after_alignment），應接近 0。
   注意：各手機各自啟動錄音，偏移＝啟動時間差＋聲學到達時間差，兩者無法從音訊分開。
2. 相位（每一對 A–B、A–C、B–C）：Welch 相干度與相位差，只在相干度 >= 0.5 有效，其餘只標記不存值；
   短時相干度與相位熱力圖；相位斜率殘餘時間差；逐 0.5 s GCC-PHAT 殘餘時間差。
3. 處理痕跡：逐 0.5 s 各軌位準（自動增益會讓軌間位準差隨響度飄）、編碼截止頻率。
4. 背景移除（特徵層，原始檔不動）：
   a. 延遲相加（各軌平均）
   b. 相干度增益：每對短時相干度扣除「錯開 1 秒對照組」的估計偏差後取平均，下限 -20 dB
   c. 穩態背景地板頻譜相減（第 10 百分位）

用法：
  python -X utf8 analyze_multi_mic.py --a A.wav --b B.wav [--c C.wav] --out <dir> [--source-note "..."]
輸入需先解碼成 wav（例如 ffmpeg -i A.webm -ac 1 -ar 48000 A.wav）。
"""
import argparse
import itertools
import json
import os

import numpy as np
import scipy.signal as ss
import soundfile as sf
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

try:
    from sync_chirp import detect_chirps
except ImportError:  # 以套件方式匯入時
    from analysis.sync_chirp import detect_chirps

plt.rcParams["font.sans-serif"] = ["Microsoft JhengHei", "Microsoft YaHei", "SimHei", "Noto Sans CJK TC", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False
COH_MIN = 0.5
PHAT_MIN = 20
COLORS = {"A": "#d62728", "B": "#1f77b4", "C": "#2ca02c"}


def db(p):
    return 10 * np.log10(np.maximum(p, 1e-20))


def log_env(x, sr, band=(200, 8000), rate=1000):
    sos = ss.butter(4, band, btype="band", fs=sr, output="sos")
    e = ss.sosfiltfilt(sos, x) ** 2
    h = sr // rate
    e = e[: len(e) // h * h].reshape(-1, h).mean(1)
    e = np.log(e + 1e-12)
    return e - e.mean()


def xcorr_peak(xs, ys, maxlag, phat):
    if phat:
        # 2026-11-10 修正：矩形切窗的帶通訊號做 PHAT 會在「窗內延遲 0」產生假峰
        # （兩段獨立噪音 PHAT 分數 145；加 Hann 窗後 5.6）。原 analyze_two_mic.py 沒有這一步。
        xs = xs * np.hanning(len(xs))
        ys = ys * np.hanning(len(ys))
    n = 1 << int(np.ceil(np.log2(len(xs) + len(ys))))
    R = np.fft.rfft(xs, n) * np.conj(np.fft.rfft(ys, n))
    if phat:
        R = R / (np.abs(R) + 1e-15)
    c = np.fft.irfft(R, n)
    c = np.concatenate([c[-maxlag:], c[: maxlag + 1]])
    k = int(np.argmax(np.abs(c)))
    d = 0.0
    if 0 < k < len(c) - 1:
        y0, y1, y2 = np.abs(c[k - 1:k + 2])
        den = y0 - 2 * y1 + y2
        d = 0.5 * (y0 - y2) / den if den != 0 else 0.0
    score = np.abs(c[k]) / (np.median(np.abs(c)) + 1e-20) if phat else \
        c[k] / np.sqrt(np.dot(xs, xs) * np.dot(ys, ys) + 1e-30)
    return k - maxlag + d, float(score)


def frac_shift(y, shift):
    """y(t + shift)，shift 單位取樣點（可為分數）。"""
    n = len(y)
    N = 1 << int(np.ceil(np.log2(n + 1)))
    Y = np.fft.rfft(y, N)
    f = np.fft.rfftfreq(N)
    return np.fft.irfft(Y * np.exp(2j * np.pi * f * shift), N)[:n]


def codec_cutoff(f, Pd):
    ref = np.median(Pd[(f > 3000) & (f < 8000)])
    above = np.where((f > 3000) & (Pd > ref - 40))[0]
    return float(f[above[-1]]) if len(above) else float(f[-1])


def load_mono(path):
    x, sr = sf.read(path, dtype="float64")
    if x.ndim > 1:
        x = x.mean(1)
    return x, sr


# ---------------------------------------------------------------- 同步
def coarse_envelope(ref, x, sr, maxlag_ms=3000):
    """回傳 (D0, info)：ref[n] 對應 x[n + D0]。"""
    ea, eb = log_env(ref, sr), log_env(x, sr)
    c = ss.correlate(ea, eb, "full")
    lags = np.arange(-len(eb) + 1, len(ea))
    k = np.abs(lags) <= maxlag_ms
    coarse_ms = int(lags[k][np.argmax(c[k])])
    r_env = float(c[k].max() / np.sqrt(np.dot(ea, ea) * np.dot(eb, eb)))
    D0 = -coarse_ms * sr // 1000
    kk = np.abs(lags) <= 1000
    curve = (-lags[kk], c[kk] / np.sqrt(np.dot(ea, ea) * np.dot(eb, eb)))
    return D0, {"method": "envelope", "coarse_offset_ms": -coarse_ms, "envelope_corr": r_env}, curve


def coarse_chirp(chirps_ref, chirps_x, sr):
    """兩軌偵測到相同數量的嗶聲、且嗶聲間隔一致（差 < 20 ms）時，用第一聲的到達時間差；否則回傳 None。"""
    if not chirps_ref or not chirps_x or len(chirps_ref) != len(chirps_x):
        return None
    gaps_ref = np.diff([c[0] for c in chirps_ref])
    gaps_x = np.diff([c[0] for c in chirps_x])
    if len(gaps_ref) and np.max(np.abs(gaps_ref - gaps_x)) > 0.020:
        return None
    t_ref, s_ref = chirps_ref[0]
    t_x, s_x = chirps_x[0]
    D0 = int(round((t_x - t_ref) * sr))
    info = {"method": "chirp", "coarse_offset_ms": 1000 * (t_x - t_ref),
            "chirp_ref_s": [c[0] for c in chirps_ref], "chirp_x_s": [c[0] for c in chirps_x],
            "chirp_scores_ref": [c[1] for c in chirps_ref], "chirp_scores_x": [c[1] for c in chirps_x]}
    if len(chirps_ref) >= 2 and len(chirps_x) >= 2:
        span_ref = chirps_ref[-1][0] - chirps_ref[0][0]
        span_x = chirps_x[-1][0] - chirps_x[0][0]
        if span_ref > 1:
            info["drift_ppm_from_chirps"] = 1e6 * (span_x - span_ref) / span_ref
    return D0, info


def fine_offset(ref, x, sr, D0, search_ms=25, exclude_s=()):
    """exclude_s：ref 上的嗶聲起點（秒）。含嗶聲的窗量到的是「主控手機→麥克風」路徑，
    不是機台路徑，會把漂移擬合拉歪（合成測試曾得 −46 ppm），所以不採用。"""
    sos = ss.butter(4, [100, min(12000, 0.45 * sr)], btype="band", fs=sr, output="sos")
    xa, xb = ss.sosfiltfilt(sos, ref), ss.sosfiltfilt(sos, x)
    win = []
    m = 2 * sr
    for t in np.arange(0.5, len(ref) / sr - 2.5, 1.0):
        i = int(t * sr)
        if i + D0 < 0 or i + D0 + m > len(xb) or i + m > len(xa):
            continue
        if any(t - 0.1 < tc + 0.6 and tc - 0.1 < t + 2.0 for tc in exclude_s):
            continue
        l, s_ = xcorr_peak(xa[i:i + m], xb[i + D0:i + D0 + m], int(search_ms / 1000 * sr), True)
        win.append((t + 1.0, D0 - l, s_))
    win = np.array(win).reshape(-1, 3)
    good = win[:, 2] >= PHAT_MIN
    if good.sum() < 2:
        raise RuntimeError(f"精對齊失敗：峰值清楚的窗只有 {int(good.sum())} 個（共 {len(win)}）；"
                           "請確認兩軌錄到同一場聲音，或在錄音開始時播放同步嗶聲")
    D = float(np.median(win[good, 1]))
    p = np.polyfit(win[good, 0], win[good, 1], 1)
    resid = win[good, 1] - np.polyval(p, win[good, 0])
    info = {"fine_offset_samples": D, "fine_offset_ms": 1000 * D / sr,
            "windows_total": int(len(win)), "windows_phat_ge_20": int(good.sum()),
            "offset_spread_p5_p95_samples": [float(np.percentile(win[good, 1], 5)),
                                             float(np.percentile(win[good, 1], 95))],
            "drift_ppm": float(1e6 * p[0] / sr), "fit_residual_std_samples": float(np.std(resid)),
            "is_integer_multiple_of_2p5ms": bool(abs(D / (0.0025 * sr) - round(D / (0.0025 * sr))) < 0.05)}
    return D, info, (win, good, p, resid)


def apply_offset(x, D):
    Di = int(np.floor(D))
    fr = D - Di
    return frac_shift(x[Di:], fr) if Di >= 0 else frac_shift(np.concatenate([np.zeros(-Di), x]), fr)


def apply_offset_drift(x, p, sr):
    """偏移隨時間線性變化時的對齊：D(t) = p[0]·t + p[1]（取樣點，t 為 A 的秒數）。
    y[n] = x[n + D(n/sr)] = x[n·(1 + a) + p[1]]，a = p[0]/sr：先平移 p[1]，再以 FFT 重取樣壓縮 (1 + a) 倍。
    不同手機各有石英振盪器，實測漂移約 20 ppm；37 秒累積約 35 取樣點，只做固定偏移會讓高頻相位隨時間旋轉。"""
    x1 = apply_offset(x, float(p[1]))
    a = float(p[0]) / sr
    return ss.resample(x1, int(round(len(x1) / (1 + a))))


# ---------------------------------------------------------------- 相位
def recursive_coh(Z1, Z2, alpha):
    S11 = np.zeros(Z1.shape[0])
    S22 = np.zeros(Z1.shape[0])
    S12 = np.zeros(Z1.shape[0], dtype=complex)
    G = np.zeros(Z1.shape)
    PH = np.zeros(Z1.shape)
    for j in range(Z1.shape[1]):
        S11 = alpha * S11 + (1 - alpha) * np.abs(Z1[:, j]) ** 2
        S22 = alpha * S22 + (1 - alpha) * np.abs(Z2[:, j]) ** 2
        S12 = alpha * S12 + (1 - alpha) * Z1[:, j] * np.conj(Z2[:, j])
        G[:, j] = np.abs(S12) ** 2 / (S11 * S22 + 1e-30)
        PH[:, j] = np.angle(S12)
    return G, PH


def pair_phase(X1, X2, sr, cut, Z1, Z2, alpha, hop, fs_):
    f, P1 = ss.welch(X1, sr, nperseg=4096)
    _, P2 = ss.welch(X2, sr, nperseg=4096)
    _, P12 = ss.csd(X1, X2, sr, nperseg=4096)
    coh = np.abs(P12) ** 2 / (P1 * P2 + 1e-30)
    ph = np.angle(P12)
    band = (f >= 50) & (f <= cut)
    valid = band & (coh >= COH_MIN)
    w = coh[valid]
    fv, pv = f[valid], np.unwrap(ph[valid])
    tau = float(np.sum(w * fv * pv) / np.sum(w * fv * fv) / (2 * np.pi)) if valid.sum() > 3 else float("nan")
    bands = [(50, 200), (200, 500), (500, 1000), (1000, 2000), (2000, 4000), (4000, 8000), (8000, cut)]
    J = {"frac_bins_coh_ge_0p5": float(valid.sum() / band.sum()),
         "residual_delay_from_phase_slope_us": 1e6 * tau,
         "coherence_median_by_band": {f"{lo}-{int(hi)}": float(np.median(coh[(f >= lo) & (f < hi)]))
                                      for lo, hi in bands if ((f >= lo) & (f < hi)).any()},
         "phase_median_deg_by_band_valid_only": {
             f"{lo}-{int(hi)}": (float(np.degrees(np.angle(np.mean(np.exp(1j * ph[(f >= lo) & (f < hi) & valid])))))
                                 if ((f >= lo) & (f < hi) & valid).any() else None) for lo, hi in bands}}
    G, PH = recursive_coh(Z1, Z2, alpha)
    sos = ss.butter(4, [100, min(12000, 0.45 * sr)], btype="band", fs=sr, output="sos")
    n = len(X1)
    tw = []
    for t in np.arange(0.0, n / sr - 1.0, 0.5):
        i = int(t * sr)
        l, s_ = xcorr_peak(ss.sosfiltfilt(sos, X1[i:i + sr]), ss.sosfiltfilt(sos, X2[i:i + sr]), int(0.003 * sr), True)
        tw.append((t + 0.5, l, s_))
    tw = np.array(tw).reshape(-1, 3)
    gk = tw[:, 2] >= PHAT_MIN
    J["residual_tdoa_windows"] = {"n": int(len(tw)), "n_phat_ge_20": int(gk.sum()),
                                  "median_samples": float(np.median(tw[gk, 1])) if gk.any() else None,
                                  "p5_p95_samples": [float(np.percentile(tw[gk, 1], 5)),
                                                     float(np.percentile(tw[gk, 1], 95))] if gk.any() else None}
    # 短時相干度偏差：第二軌錄音錯開 1 秒的對照組
    sh = int(sr / hop)
    G0 = np.zeros((Z1.shape[0], max(Z1.shape[1] - sh, 1)))
    if Z1.shape[1] > sh:
        G0, _ = recursive_coh(Z1[:, sh:], Z2[:, :Z1.shape[1] - sh], alpha)
    Gamma0 = np.median(G0, axis=1)[:, None]
    Gc = np.clip((G - Gamma0) / (1 - Gamma0), 0.01, 1.0)
    m = (fs_ >= 100) & (fs_ <= cut)
    J["short_time_coherence_bias_control_median"] = float(np.median(Gamma0[m]))
    J["short_time_coherence_real_median"] = float(np.median(G[m]))
    arrays = {"f": f, "coh": coh, "ph": ph, "band": band, "valid": valid, "tau": tau, "G": G, "PH": PH,
              "tw": tw, "gk": gk, "Gc": Gc}
    return J, arrays


# ---------------------------------------------------------------- 主程式
def run(paths, out, note=""):
    """paths: {"A": path, "B": path, ["C": path]}。回傳 summary dict（也寫入 out/summary.json）。"""
    os.makedirs(out, exist_ok=True)
    labels = [k for k in ("A", "B", "C") if paths.get(k)]
    assert len(labels) >= 2 and labels[0] == "A", "至少需要 A 與 B"
    raw, sr = {}, None
    for k in labels:
        raw[k], s = load_mono(paths[k])
        assert sr is None or s == sr, "各檔取樣率不同，請先統一重取樣"
        sr = s
    J = {"input": {k: {"file": os.path.basename(paths[k]), "len_s": len(raw[k]) / sr} for k in labels},
         "sr": sr, "note": note, "channels": labels}

    # 1. 同步：各軌對齊到 A
    chirps = {k: detect_chirps(raw[k], sr) for k in labels}
    J["sync_chirps_detected_s"] = {k: [round(c[0], 4) for c in chirps[k]] for k in labels}
    aligned = {"A": raw["A"]}
    J["sync"] = {}
    plots = {}
    for k in labels[1:]:
        ch = coarse_chirp(chirps["A"], chirps[k], sr)
        if ch is not None:
            D0, cinfo = ch
            curve = None
        else:
            D0, cinfo, curve = coarse_envelope(raw["A"], raw[k], sr)
        excl = [c[0] for c in chirps["A"]]
        D, finfo, fit = fine_offset(raw["A"], raw[k], sr, D0, exclude_s=excl)
        if finfo["windows_phat_ge_20"] >= 5 and abs(finfo["drift_ppm"]) >= 0.5:
            aligned[k] = apply_offset_drift(raw[k], fit[2], sr)
            finfo["drift_compensated"] = True
        else:
            aligned[k] = apply_offset(raw[k], D)
            finfo["drift_compensated"] = False
        # 驗證：對齊後再量一次，偏移應接近 0、漂移接近 0
        try:
            _, vinfo, _ = fine_offset(raw["A"], aligned[k], sr, 0, search_ms=5, exclude_s=excl)
            finfo["after_alignment"] = {k_: vinfo[k_] for k_ in ("fine_offset_samples", "drift_ppm",
                                                                   "offset_spread_p5_p95_samples",
                                                                   "fit_residual_std_samples", "windows_phat_ge_20")}
        except RuntimeError as e:
            finfo["after_alignment"] = {"error": str(e)}
        J["sync"][f"{k}_vs_A"] = {"coarse": cinfo, **finfo}
        plots[k] = (curve, fit, D, finfo)
    n = min(len(v) for v in aligned.values())
    X = {k: aligned[k][:n] for k in labels}
    for k in labels:
        sf.write(os.path.join(out, f"{k}_aligned.wav"), X[k].astype(np.float32), sr, subtype="FLOAT")
    J["aligned_length_s"] = n / sr

    # 2. 相位（逐對）
    nf, hop, alpha = 4096, 1024, 0.8
    Z = {}
    for k in labels:
        fs_, ts, Z[k] = ss.stft(X[k], sr, nperseg=nf, noverlap=nf - hop)
    cuts = {}
    for k in labels:
        f_, Pk = ss.welch(X[k], sr, nperseg=4096)
        cuts[k] = codec_cutoff(f_, db(Pk))
    cut = min(cuts.values())
    J["codec_cutoff_hz"] = {**cuts, "used": cut}
    pairs = list(itertools.combinations(labels, 2))
    J["phase"] = {}
    PA = {}
    for a_, b_ in pairs:
        J["phase"][f"{a_}-{b_}"], PA[(a_, b_)] = pair_phase(X[a_], X[b_], sr, cut, Z[a_], Z[b_], alpha, hop, fs_)

    # 3. 處理痕跡
    seg = int(0.5 * sr)
    lv = {k: np.array([20 * np.log10(np.std(X[k][i:i + seg]) + 1e-12) for i in range(0, n - seg, seg)]) for k in labels}
    tlv = (np.arange(len(lv["A"])) * seg + seg / 2) / sr
    mean_lv = np.mean([lv[k] for k in labels], axis=0)
    J["processing_check"] = {}
    for a_, b_ in pairs:
        d = lv[a_] - lv[b_]
        J["processing_check"][f"level_diff_{a_}_minus_{b_}_db"] = {
            "median": float(np.median(d)), "p5_p95": [float(np.percentile(d, 5)), float(np.percentile(d, 95))],
            "corr_with_level": float(np.corrcoef(d, mean_lv)[0, 1])}

    # 4. 背景移除
    ZS = np.mean([Z[k] for k in labels], axis=0)
    Gc = np.mean([PA[p]["Gc"] for p in pairs], axis=0)
    PS = np.abs(ZS) ** 2
    floor = np.percentile(PS, 10, axis=1)[:, None]
    Gf = np.maximum(1 - floor / np.maximum(PS, 1e-30), 0.01)
    lp = (fs_ <= cut)[:, None]
    versions = {"delay_and_sum": ZS * lp,
                "coherence_filtered": ZS * np.sqrt(Gc) * lp,
                "final_coherence_plus_floor": ZS * np.sqrt(Gc * Gf) * lp}
    versions["removed_part"] = ZS * lp - versions["final_coherence_plus_floor"]
    outs, P = {}, {}
    for name, Zv in versions.items():
        _, y = ss.istft(Zv, sr, nperseg=nf, noverlap=nf - hop)
        y = y[:n]
        sf.write(os.path.join(out, f"{name}.wav"), y.astype(np.float32), sr, subtype="FLOAT")
        outs[name] = float(20 * np.log10(np.std(y) + 1e-20))
        P[name] = np.abs(Zv) ** 2
    mband = (fs_ >= 100) & (fs_ <= cut)
    fe = PS[mband].sum(0)
    q_lo, q_hi = np.percentile(fe, 20), np.percentile(fe, 80)
    fin = P["final_coherence_plus_floor"][mband].sum(0)
    att = 10 * np.log10(fin / np.maximum(fe, 1e-30))
    J["background_removal"] = {
        "rms_dbfs": {**{f"{k}_aligned": float(20 * np.log10(np.std(X[k]) + 1e-20)) for k in labels}, **outs},
        "attenuation_db_quiet_frames_bottom20pct": float(np.median(att[fe <= q_lo])),
        "attenuation_db_loud_frames_top20pct": float(np.median(att[fe >= q_hi])),
        "mean_coherence_gain_db": float(10 * np.log10(np.mean(Gc[mband]))),
        "settings": {"stft": [nf, hop], "coherence_alpha": alpha, "gain_floor_db": -20, "floor_percentile": 10,
                     "pairs_averaged": [f"{a_}-{b_}" for a_, b_ in pairs]}}

    # ---------------------------------------------------------------- 圖
    # 圖 1：同步
    others = labels[1:]
    fig, axs = plt.subplots(len(others) + 1, 1, figsize=(14, 4 + 3.5 * len(others)))
    for ax, k in zip(axs, others):
        curve, (win, good, p, resid), D, finfo = plots[k]
        ax.plot(win[good, 0], win[good, 1], "o", ms=4, color=COLORS[k], label="GCC-PHAT 峰值清楚的窗")
        ax.plot(win[~good, 0], win[~good, 1], "x", ms=5, color="#bbbbbb", label="峰值不清楚（不採用）")
        ax.plot(win[:, 0], np.polyval(p, win[:, 0]), "k-", lw=1, label=f"直線擬合：漂移 {finfo['drift_ppm']:+.2f} ppm")
        ax.set_ylim(D - 3, D + 3)
        how = J["sync"][f"{k}_vs_A"]["coarse"]["method"]
        ax.set_title(f"{k} 對 A：粗對齊用{'同步嗶聲' if how == 'chirp' else '能量包絡'}；"
                     f"精對齊 {D:.2f} 取樣點 = {1000 * D / sr:.3f} ms（{k} 比 A 晚為正）")
        ax.set_ylabel(f"{k} - A 偏移（取樣點）")
        ax.legend(fontsize=8)
    ax = axs[-1]
    for k in labels:
        ax.plot(tlv, lv[k], color=COLORS[k], lw=0.9, label=f"{k} 位準")
    ax.set_title("對齊後每 0.5 秒位準；若手機做了自動增益，軌間差會隨響度變動")
    ax.set_ylabel("dBFS")
    ax.set_xlabel("時間 s")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(out, "fig1_sync.png"), dpi=110)
    plt.close(fig)

    # 圖 2：逐對相位
    for (a_, b_), A_ in PA.items():
        f, coh, ph, band, valid, tau = A_["f"], A_["coh"], A_["ph"], A_["band"], A_["valid"], A_["tau"]
        tw, gk, G, PH = A_["tw"], A_["gk"], A_["G"], A_["PH"]
        fig = plt.figure(figsize=(16, 12))
        gs = fig.add_gridspec(3, 2, height_ratios=[1, 1, 1.3])
        ax = fig.add_subplot(gs[0, 0])
        ax.semilogx(f[band], coh[band], color="k", lw=0.6)
        ax.axhline(COH_MIN, color="r", ls="--", lw=1)
        ax.set_ylim(0, 1.02)
        ax.set_title(f"{a_}–{b_} 相干度（全段平均；>=0.5 佔 {100 * valid.sum() / band.sum():.0f}% 頻帶）")
        ax.set_xlabel("Hz")
        ax = fig.add_subplot(gs[0, 1])
        ax.semilogx(f[valid], np.degrees(ph[valid]), ".", ms=3, color="#1f77b4", label="有效（相干 >= 0.5）")
        iv = band & ~valid
        ax.semilogx(f[iv], np.full(iv.sum(), -200), "|", ms=3, color="#bbbbbb", label="無效（只標記）")
        if np.isfinite(tau) and valid.sum() / band.sum() >= 0.02:
            ax.semilogx(f[band], np.degrees(np.angle(np.exp(2j * np.pi * f[band] * tau))), "r-", lw=0.8,
                        label=f"相位斜率對應殘餘時間差 {1e6 * tau:+.1f} µs")
        ax.set_ylim(-210, 190)
        ax.set_title(f"{a_}–{b_} 相位差（只畫有效頻帶）")
        ax.set_xlabel("Hz")
        ax.set_ylabel("度")
        ax.legend(fontsize=7)
        ax = fig.add_subplot(gs[1, :])
        ax.plot(tw[gk, 0], 1e3 * tw[gk, 1] / sr, "o", ms=3, color="#1f77b4", label="峰值清楚")
        ax.plot(tw[~gk, 0], 1e3 * tw[~gk, 1] / sr, "x", ms=4, color="#bbbbbb", label="峰值不清楚")
        ax.axhline(0, color="k", lw=0.5)
        ax.set_title(f"對齊後逐 0.5 秒的殘餘到達時間差（{a_}–{b_}，GCC-PHAT）：主聲源方向是否穩定")
        ax.set_ylabel(f"ms（+ ＝ {b_} 較晚）")
        ax.set_xlabel("時間 s")
        ax.legend(fontsize=8)
        ax = fig.add_subplot(gs[2, 0])
        im = ax.imshow(G, origin="lower", aspect="auto", cmap="viridis", extent=[ts[0], ts[-1], 0, fs_[-1]], vmin=0, vmax=1)
        ax.set_ylim(0, cut)
        ax.set_title("短時相干度（時間 × 頻率）")
        ax.set_xlabel("時間 s")
        ax.set_ylabel("Hz")
        fig.colorbar(im, ax=ax)
        ax = fig.add_subplot(gs[2, 1])
        PHm = np.where(G >= COH_MIN, np.degrees(PH), np.nan)
        cm = plt.get_cmap("twilight").copy()
        cm.set_bad("#d9d9d9")
        im = ax.imshow(PHm, origin="lower", aspect="auto", cmap=cm, extent=[ts[0], ts[-1], 0, fs_[-1]], vmin=-180, vmax=180)
        ax.set_ylim(0, cut)
        ax.set_title("相位差熱力圖（灰＝相干度 < 0.5，相位無效）")
        ax.set_xlabel("時間 s")
        fig.colorbar(im, ax=ax, label="度")
        fig.tight_layout()
        fig.savefig(os.path.join(out, f"fig2_phase_{a_}{b_}.png"), dpi=105)
        plt.close(fig)

    # 圖 3、4：背景移除
    fig, axs = plt.subplots(2, 2, figsize=(17, 10), sharex=True, sharey=True)
    ref = db(np.abs(Z["A"]) ** 2).max()
    items = [("A 原始（對齊後）", np.abs(Z["A"]) ** 2), (f"延遲相加（{'+'.join(labels)} 平均）", P["delay_and_sum"]),
             ("相干度增益 + 地板相減（最終）", P["final_coherence_plus_floor"]), ("被移除的部分", P["removed_part"])]
    for ax, (tt, PP) in zip(axs.flat, items):
        ax.imshow(db(PP), origin="lower", aspect="auto", cmap="magma", extent=[ts[0], ts[-1], 0, fs_[-1]],
                  vmin=ref - 90, vmax=ref)
        ax.set_ylim(0, cut)
        ax.set_title(tt)
    for ax in axs[:, 0]:
        ax.set_ylabel("Hz")
    for ax in axs[1]:
        ax.set_xlabel("時間 s")
    fig.tight_layout()
    fig.savefig(os.path.join(out, "fig3_background_removal.png"), dpi=100)
    plt.close(fig)

    fig, axs = plt.subplots(1, 2, figsize=(17, 5))
    ax = axs[0]
    for k in labels:
        ax.semilogx(fs_, db((np.abs(Z[k]) ** 2).mean(1)), lw=0.8, color=COLORS[k], label=f"{k} 原始")
    for name, col in [("delay_and_sum", "#7f7f7f"), ("final_coherence_plus_floor", "k"), ("removed_part", "#9467bd")]:
        ax.semilogx(fs_, db(P[name].mean(1)), lw=0.8, color=col,
                    label={"delay_and_sum": "延遲相加", "final_coherence_plus_floor": "最終", "removed_part": "被移除"}[name])
    ax.semilogx(fs_, db(floor[:, 0]), "--", lw=0.8, color="#8c564b", label="穩態地板（第 10 百分位）")
    ax.set_xlim(30, cut * 1.2)
    ax.set_ylim(db(np.abs(Z["A"]) ** 2).mean(1).max() - 90, None)
    ax.set_title("處理前後的平均頻譜")
    ax.set_xlabel("Hz")
    ax.legend(fontsize=7)
    ax = axs[1]
    tt = ts[: len(fe)]
    ax.plot(tt, 10 * np.log10(fe + 1e-30), color="#7f7f7f", lw=0.8, label="延遲相加")
    ax.plot(tt, 10 * np.log10(fin + 1e-30), color="k", lw=0.8, label="最終")
    br = J["background_removal"]
    ax.set_title(f"每幀能量：安靜幀衰減 {br['attenuation_db_quiet_frames_bottom20pct']:.1f} dB，"
                 f"響幀衰減 {br['attenuation_db_loud_frames_top20pct']:.1f} dB")
    ax.set_xlabel("時間 s")
    ax.set_ylabel("dB")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(out, "fig4_removal_spectra.png"), dpi=105)
    plt.close(fig)

    with open(os.path.join(out, "summary.json"), "w", encoding="utf-8") as fh:
        json.dump(J, fh, ensure_ascii=False, indent=2)
    return J


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--a", required=True, help="聲源 A（主控手機）wav")
    ap.add_argument("--b", required=True, help="聲源 B wav")
    ap.add_argument("--c", default=None, help="聲源 C wav（可省略）")
    ap.add_argument("--out", required=True)
    ap.add_argument("--source-note", default="")
    args = ap.parse_args()
    J = run({"A": args.a, "B": args.b, "C": args.c}, args.out, args.source_note)
    print(json.dumps({"sync": J["sync"], "background_removal": J["background_removal"]}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
