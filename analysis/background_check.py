"""background_check.py — 雙聲道同一時鐘的錄音（例如 miniDSP EARS）能把背景音消掉多少。

用途：到機台旁先錄一段「只有背景音」的錄音，回答「用一支麥克風預測另一支、再相減」這種背景過濾值不值得做。

  python -X utf8 analysis/record_usb.py record --stereo E.A.R.S --seconds 60 --out D:/cnc_offline/bg1
  python -X utf8 analysis/background_check.py --stereo D:/cnc_offline/bg1/stereo.wav --out D:/cnc_offline/bg1/background

每個頻段給兩個數字：
1. 相干度上限：兩軌的相干度 γ² 決定理論上最多能消掉多少，殘餘功率比例 = 1 − γ²。
   γ² = 0.5 最多消 3 dB，0.9 最多消 10 dB，0.99 最多消 20 dB。
2. 實際做到：用錄音的前半段估計「左軌 → 右軌」的轉移函數，套到後半段相減，量後半段真的少了多少。
   用沒看過的後半段驗收，所以背景聲源移動、時大時小時，這個數字會比上限差；它比上限更接近實際能得到的效果。

兩個方向都算（用左預測右、用右預測左）。輸出資料夾必須在 Git 儲存庫外。
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import scipy.signal as ss
import soundfile as sf

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from offline import decode_stereo, inside_repo  # noqa: E402

NPERSEG = 8192                       # 48 kHz 時頻率解析度 5.9 Hz
FIR_TAPS = 4096                      # 轉移函數的濾波器長度（±2048 取樣點＝±43 ms，容得下兩支麥克風之間的到達時間差與早期反射）
BANDS = ((50, 100), (100, 200), (200, 400), (400, 800), (800, 1600), (1600, 3150), (3150, 6300), (6300, 12500))
MIN_SECONDS = 20.0


def _db(x):
    return float(10 * np.log10(max(float(x), 1e-30)))


def spectra(a, b, sr):
    f, paa = ss.welch(a, sr, nperseg=NPERSEG)
    _, pbb = ss.welch(b, sr, nperseg=NPERSEG)
    _, pab = ss.csd(a, b, sr, nperseg=NPERSEG)
    return f, paa, pbb, pab


def transfer_fir(src, dst, sr):
    """最小平方意義下「src → dst」的轉移函數 H = P_sd / P_ss，轉成長度 FIR_TAPS、置中的 FIR（離線使用，允許非因果）。"""
    _, pss, _, psd = spectra(src, dst, sr)
    h = np.fft.irfft(psd / (pss + 1e-30 * np.max(pss) + 1e-30), NPERSEG)
    h = np.roll(h, FIR_TAPS // 2)[:FIR_TAPS] * np.hanning(FIR_TAPS)
    return h


def apply_fir(h, x):
    y = ss.fftconvolve(x, h, mode="full")
    return y[FIR_TAPS // 2:FIR_TAPS // 2 + len(x)]


def band_power(f, p, lo, hi):
    m = (f >= lo) & (f < hi)
    return float(np.sum(p[m])) if m.any() else 0.0


def analyse(a, b, sr, train_fraction=0.5):
    """a、b：同一時鐘的兩軌。回傳各頻段的相干度上限與實際消除量（負值＝變小）。"""
    n = min(len(a), len(b))
    a, b = np.asarray(a[:n], float), np.asarray(b[:n], float)
    if n / sr < MIN_SECONDS:
        raise ValueError(f"錄音只有 {n / sr:.1f} 秒；至少需要 {MIN_SECONDS:g} 秒，建議 60 秒以上")
    f, paa, pbb, pab = spectra(a, b, sr)
    coh = np.abs(pab) ** 2 / (paa * pbb + 1e-30)
    k = int(n * train_fraction)
    tr_a, tr_b, te_a, te_b = a[:k], b[:k], a[k:], b[k:]
    res_b = te_b - apply_fir(transfer_fir(tr_a, tr_b, sr), te_a)      # 用 A 預測 B
    res_a = te_a - apply_fir(transfer_fir(tr_b, tr_a, sr), te_b)      # 用 B 預測 A
    edge = FIR_TAPS                                                   # 濾波器兩端的暫態不算
    sl = slice(edge, -edge)
    ft, p_tb = ss.welch(te_b[sl], sr, nperseg=NPERSEG)
    _, p_ta = ss.welch(te_a[sl], sr, nperseg=NPERSEG)
    _, p_rb = ss.welch(res_b[sl], sr, nperseg=NPERSEG)
    _, p_ra = ss.welch(res_a[sl], sr, nperseg=NPERSEG)
    rows = []
    for lo, hi in BANDS:
        if hi > sr / 2:
            continue
        m = (f >= lo) & (f < hi)
        pa, pb = band_power(f, paa, lo, hi), band_power(f, pbb, lo, hi)
        rows.append({
            "band_hz": f"{lo}-{hi}",
            "level_a_dbfs": round(_db(pa * (f[1] - f[0])), 1), "level_b_dbfs": round(_db(pb * (f[1] - f[0])), 1),
            "coherence_median": round(float(np.median(coh[m])), 3),
            "limit_db_predict_b": round(_db(np.sum(pbb[m] * (1 - coh[m])) / (pb + 1e-30)), 1),
            "limit_db_predict_a": round(_db(np.sum(paa[m] * (1 - coh[m])) / (pa + 1e-30)), 1),
            "achieved_db_predict_b": round(_db(band_power(ft, p_rb, lo, hi) / (band_power(ft, p_tb, lo, hi) + 1e-30)), 1),
            "achieved_db_predict_a": round(_db(band_power(ft, p_ra, lo, hi) / (band_power(ft, p_ta, lo, hi) + 1e-30)), 1),
        })
    wide = (ft >= BANDS[0][0]) & (ft < min(BANDS[-1][1], sr / 2))
    peak = float(max(np.max(np.abs(a)), np.max(np.abs(b))))
    return {"duration_s": round(n / sr, 2), "sample_rate": sr, "train_seconds": round(k / sr, 2),
            "test_seconds": round((n - k) / sr, 2), "peak": round(peak, 4), "clipped": bool(peak >= 0.999),
            "level_dbfs": {"A": round(_db(np.var(a)), 1), "B": round(_db(np.var(b)), 1)},
            "overall_achieved_db": {"predict_b": round(_db(np.sum(p_rb[wide]) / np.sum(p_tb[wide])), 1),
                                    "predict_a": round(_db(np.sum(p_ra[wide]) / np.sum(p_ta[wide])), 1)},
            "bands": rows,
            "settings": {"nperseg": NPERSEG, "fir_taps": FIR_TAPS, "train_fraction": train_fraction}}, (f, coh)


def verdict_text(row):
    best = min(row["achieved_db_predict_a"], row["achieved_db_predict_b"])
    if best <= -10:
        return "有效"
    if best <= -5:
        return "部分有效"
    return "效果很小"


def print_result(res):
    print(f"錄音 {res['duration_s']} 秒：前 {res['train_seconds']} 秒估計轉移函數，後 {res['test_seconds']} 秒驗收。"
          f"整體位準 A {res['level_dbfs']['A']}、B {res['level_dbfs']['B']} dBFS，峰值 {res['peak']}")
    if res["clipped"]:
        print("注意：錄音破音（峰值到滿刻度），結果不可靠，請調低增益重錄")
    print("頻段 Hz      位準 A/B dBFS   相干度   上限 dB(預測B/預測A)   實際 dB(預測B/預測A)   判讀")
    for r in res["bands"]:
        print(f"{r['band_hz']:>11s}  {r['level_a_dbfs']:6.1f}/{r['level_b_dbfs']:<6.1f}   {r['coherence_median']:5.3f}    "
              f"{r['limit_db_predict_b']:6.1f}/{r['limit_db_predict_a']:<6.1f}        "
              f"{r['achieved_db_predict_b']:6.1f}/{r['achieved_db_predict_a']:<6.1f}      {verdict_text(r)}")
    o = res["overall_achieved_db"]
    print(f"整體（{BANDS[0][0]}–{BANDS[-1][1]} Hz）實際消除：預測 B {o['predict_b']} dB、預測 A {o['predict_a']} dB（負值＝變小）")


def save_figure(res, f, coh, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams["font.sans-serif"] = ["Microsoft JhengHei", "Microsoft YaHei", "SimHei"]
    plt.rcParams["axes.unicode_minus"] = False
    fig, ax = plt.subplots(2, 1, figsize=(11, 8))
    m = (f >= BANDS[0][0]) & (f <= min(BANDS[-1][1], f[-1]))
    ax[0].semilogx(f[m], coh[m], lw=0.7)
    ax[0].set_ylim(0, 1.02)
    ax[0].set_ylabel("兩軌相干度 γ²")
    ax[0].set_title("背景音在兩支麥克風之間的相干度（越接近 1，越能互相抵消）")
    ax[0].grid(alpha=0.3)
    x = np.arange(len(res["bands"]))
    ax[1].bar(x - 0.2, [min(r["limit_db_predict_b"], r["limit_db_predict_a"]) for r in res["bands"]], 0.4,
              label="相干度上限", color="#bbbbbb")
    ax[1].bar(x + 0.2, [min(r["achieved_db_predict_b"], r["achieved_db_predict_a"]) for r in res["bands"]], 0.4,
              label="實際做到（後半段驗收）", color="#1f77b4")
    ax[1].set_xticks(x)
    ax[1].set_xticklabels([r["band_hz"] for r in res["bands"]])
    ax[1].axhline(-10, color="r", ls=":", lw=0.8)
    ax[1].set_ylabel("背景音變化 dB（越負越好）")
    ax[1].set_xlabel("頻段 Hz")
    ax[1].legend(fontsize=8)
    ax[1].grid(alpha=0.3, axis="y")
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


def cmd(args):
    out = Path(args.out)
    if inside_repo(out):
        raise SystemExit("輸出不可放在 Git 儲存庫內，請改到儲存庫外的資料夾")
    src = Path(args.stereo)
    if not src.is_file():
        raise SystemExit(f"找不到檔案：{src}")
    (out / "input").mkdir(parents=True, exist_ok=True)
    wa, wb = out / "input" / "A.wav", out / "input" / "B.wav"
    decode_stereo(src, wa, wb)
    a, sr = sf.read(str(wa), dtype="float64")
    b, _ = sf.read(str(wb), dtype="float64")
    try:
        res, (f, coh) = analyse(a, b, sr)
    except ValueError as e:
        raise SystemExit(str(e))
    res["source"] = src.name
    res["note"] = args.note
    with open(out / "background_check.json", "w", encoding="utf-8") as fh:
        json.dump(res, fh, ensure_ascii=False, indent=2)
    save_figure(res, f, coh, out / "background_check.png")
    print_result(res)
    print(f"\n圖與數字：{out}（background_check.png、background_check.json）")
    return res


def main(argv=None):
    ap = argparse.ArgumentParser(description="雙聲道同一時鐘錄音的背景音可消除量")
    ap.add_argument("--stereo", required=True, help="雙聲道錄音（左＝A、右＝B），只含背景音，建議 60 秒以上")
    ap.add_argument("--out", required=True, help="輸出資料夾（儲存庫外）")
    ap.add_argument("--note", default="", help="這段錄音的說明：地點、機台狀態、麥克風位置")
    return cmd(ap.parse_args(argv))


if __name__ == "__main__":
    main()
