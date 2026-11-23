"""offline.py — 不經過網站資料庫，直接分析三支手機的錄音檔。

用途：網站還沒有正式主機、或錄音網站的版本沒有地端分析佇列時，先用真實收音驗證對齊與相位。

1. 產生同步嗶聲檔（由第四台裝置播放；錄音開頭、結尾各播一次）：
     python -X utf8 analysis/offline.py chirp --out D:/cnc_offline/sync_chirp.wav
2. 分析（任何 ffmpeg 讀得懂的格式：網站下載的 webm、手機錄音 App 的 m4a、wav 都可以）：
     python -X utf8 analysis/offline.py run --a A.webm --b B.webm --c C.webm --out D:/cnc_offline/run1 --note "風扇測試"
3. 雙聲道裝置（例如 miniDSP EARS：左右兩支麥克風同一個時鐘）加一支獨立麥克風（例如 UMIK-2）：
     python -X utf8 analysis/offline.py run --stereo-ab ears.wav --c umik2.wav --ab-spacing-m 0.15 --out D:/cnc_offline/run2
   A＝左聲道、B＝右聲道。兩軌同一時鐘，所以不對齊，量到的 A–B 時間差就是聲學到達時間差；C 照舊對齊到 A。
   錄音用 analysis/record_usb.py。

輸出資料夾：input/（解碼後的 48 kHz 單聲道 wav）、模型的圖與 summary.json、offline_report.json。
錄音與輸出都不可放進 Git 儲存庫（本程式會拒絕寫進儲存庫資料夾）。
"""
import argparse
import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))

from sync_chirp import chirp_template  # noqa: E402

SR = 48000
LABELS = ("A", "B", "C")
# 不自動判定「有沒有自動增益」：機台停機時各軌只剩各自的底噪，位準差本來就會跟著響度變，
# 合成資料（固定增益）的相關係數就有 0.97–0.99。只列數字，判讀要配合錄音過程。


def inside_repo(p):
    p = Path(p).resolve()
    return p == REPO or REPO in p.parents


def ffmpeg_exe():
    import shutil
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def decode(src, wav, sr=SR):
    cmd = [ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y", "-i", str(src),
           "-ac", "1", "-ar", str(sr), "-c:a", "pcm_f32le", str(wav)]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if p.returncode != 0 or not Path(wav).exists():
        raise SystemExit(f"解碼失敗：{src}\n{p.stderr[-1500:]}")


def decode_stereo(src, wav_left, wav_right, sr=SR):
    """把雙聲道檔拆成左、右兩個單聲道 wav（不混音：混成單聲道會失去兩支麥克風之間的相位差）。"""
    tmp = Path(wav_left).with_name("_stereo_tmp.wav")
    cmd = [ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y", "-i", str(src),
           "-ar", str(sr), "-c:a", "pcm_f32le", str(tmp)]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if p.returncode != 0 or not tmp.exists():
        raise SystemExit(f"解碼失敗：{src}\n{p.stderr[-1500:]}")
    try:
        y, got_sr = sf.read(str(tmp), dtype="float32", always_2d=True)
    finally:
        tmp.unlink(missing_ok=True)
    if y.shape[1] != 2:
        raise SystemExit(f"{Path(src).name} 不是雙聲道檔（聲道數 {y.shape[1]}）；--stereo-ab 需要左右兩軌")
    if np.max(np.abs(y[:, 0] - y[:, 1])) < 1e-6:
        raise SystemExit(f"{Path(src).name} 的左右兩軌完全相同：錄到的是單聲道複製成雙聲道，不是兩支麥克風。"
                         "請檢查 Windows 音效設定的輸入格式是否為 2 聲道")
    sf.write(str(wav_left), y[:, 0], got_sr, subtype="FLOAT")
    sf.write(str(wav_right), y[:, 1], got_sr, subtype="FLOAT")


def write_chirp(out, sr=SR, pad_s=0.5):
    tpl = chirp_template(sr)
    pad = np.zeros(int(round(pad_s * sr)))
    y = np.concatenate([pad, tpl, pad])
    sf.write(str(out), y.astype(np.float32), sr, subtype="PCM_16")
    return len(y) / sr


def _num(v, nd=2):
    return round(float(v), nd) if isinstance(v, (int, float)) and math.isfinite(v) else None


def report(J):
    """從 summary.json 摘出判讀需要的數字，加上對齊判定（與地端 worker 同一套標準）。"""
    from worker import alignment_verdict
    verdict = alignment_verdict(J)
    pairs = {}
    for k in J.get("channels", [])[1:]:
        s = J["sync"].get(f"{k}_vs_A", {})
        c = s.get("coarse", {})
        aa = s.get("after_alignment", {}) or {}
        if s.get("same_clock"):
            sp = s.get("spacing") or {}
            pairs[f"{k}_vs_A"] = {
                "same_clock": True, "aligned": False,
                "acoustic_tdoa_samples": _num(s.get("acoustic_tdoa_samples")),
                "acoustic_tdoa_us": _num(s.get("acoustic_tdoa_us"), 1),
                "tdoa_spread_p5_p95_samples": [_num(x) for x in s.get("tdoa_spread_p5_p95_samples", [])],
                "tdoa_trend_ppm": _num(s.get("tdoa_trend_ppm")),
                "clear_windows": f"{s.get('windows_phat_ge_20')}/{s.get('windows_total')}",
                "spacing_m": sp.get("spacing_m"), "max_tdoa_samples": _num(sp.get("max_tdoa_samples")),
                "aliasing_hz": _num(sp.get("aliasing_hz"), 0),
                "tdoa_over_straight_line_limit": sp.get("tdoa_over_straight_line_limit"),
                "warning": s.get("clock_warning") or s.get("tdoa_error")}
            continue
        pairs[f"{k}_vs_A"] = {
            "coarse_method": c.get("method"),
            "coarse_offset_ms": _num(c.get("coarse_offset_ms")),
            "drift_ppm_from_chirps": _num(c.get("drift_ppm_from_chirps")),
            "fine_offset_samples": _num(s.get("fine_offset_samples")),
            "drift_ppm": _num(s.get("drift_ppm")),
            "clear_windows": f"{s.get('windows_phat_ge_20')}/{s.get('windows_total')}",
            "drift_compensated": s.get("drift_compensated"),
            "after_alignment_offset_samples": _num(aa.get("fine_offset_samples")),
            "after_alignment_drift_ppm": _num(aa.get("drift_ppm")),
        }
    agc = {}
    for name, v in (J.get("processing_check") or {}).items():
        r = v.get("corr_with_level")
        agc[name] = {"median_db": _num(v.get("median")), "p5_p95_db": [_num(x) for x in v.get("p5_p95", [])],
                     "corr_with_level": _num(r)}
    phase = {p: {"frac_bins_coherence_ge_0p5": _num(v.get("frac_bins_coh_ge_0p5"), 3),
                 "residual_delay_from_phase_slope_us": _num(v.get("residual_delay_from_phase_slope_us"), 1)}
             for p, v in (J.get("phase") or {}).items()}
    return {"alignment": verdict,
            "durations_s": {k: _num(v.get("len_s")) for k, v in J.get("input", {}).items()},
            "chirps_detected_s": J.get("sync_chirps_detected_s"),
            "pairs": pairs, "codec_cutoff_hz": J.get("codec_cutoff_hz"),
            "level_difference": agc, "phase": phase,
            "note": J.get("note", "")}


def print_report(R):
    v = R["alignment"]
    print("== 對齊判定 ==")
    same = v.get("same_clock_pairs") or []
    if v["verified"] and len(same) == len(v["channels"]) - 1:
        print(f"  {'、'.join(v['channels'])} 同一時鐘，硬體同步，不需要對齊（沒有對齊殘差可驗證）")
    elif v["verified"]:
        print(f"  已驗證：{'、'.join(v['channels'])} 共 {len(v['channels'])} 軌，殘餘偏移 ≤ "
              f"{v['criteria']['max_residual_samples']:g} 取樣點、殘餘漂移 ≤ {v['criteria']['max_residual_ppm']:g} ppm")
        if same:
            print(f"  其中 {'、'.join(same)} 是同一時鐘，硬體同步，不經過對齊")
    else:
        print("  未通過，同步與相位數字不可使用：" + "；".join(f"{k} {m}" for k, m in v["failed_pairs"].items()))
    print("== 各軌 ==")
    print("  時長（秒）：" + "、".join(f"{k} {s}" for k, s in R["durations_s"].items()))
    print("  偵測到的嗶聲（秒）：" + "；".join(f"{k} {s}" for k, s in (R["chirps_detected_s"] or {}).items()))
    print(f"  編碼截止頻率（Hz）：{R['codec_cutoff_hz']}")
    for name, p in R["pairs"].items():
        print(f"== {name} ==")
        if p.get("same_clock") and p["acoustic_tdoa_samples"] is None:
            print("  同一時鐘，不對齊。聲學到達時間差量不到：兩軌之間沒有夠清楚的共同聲源"
                  "（環境音太分散，或聲源太小聲）。請用一個明確的聲源再錄一次。")
            continue
        if p.get("same_clock"):
            print(f"  同一時鐘，不對齊。聲學到達時間差 {p['acoustic_tdoa_samples']} 取樣點（{p['acoustic_tdoa_us']} µs），"
                  f"5–95% {p['tdoa_spread_p5_p95_samples']}，隨時間趨勢 {p['tdoa_trend_ppm']} ppm（清楚窗 {p['clear_windows']}）")
            if p["spacing_m"]:
                over = "；超過直線間距上限（治具繞射或間距偏小）" if p["tdoa_over_straight_line_limit"] else ""
                print(f"  間距 {p['spacing_m']} m：直線上限 ±{p['max_tdoa_samples']} 取樣點，"
                      f"相位不混疊的頻率上限 {p['aliasing_hz']} Hz{over}")
            if p["warning"]:
                print(f"  注意：{p['warning']}")
            continue
        print(f"  粗對齊：{p['coarse_method']}，{p['coarse_offset_ms']} ms；精對齊偏移 {p['fine_offset_samples']} 取樣點，"
              f"漂移 {p['drift_ppm']} ppm（清楚窗 {p['clear_windows']}，嗶聲估計 {p['drift_ppm_from_chirps']} ppm）")
        print(f"  對齊後重量：偏移 {p['after_alignment_offset_samples']} 取樣點，漂移 {p['after_alignment_drift_ppm']} ppm")
    print("== 軌間位準差（停機與運轉混在一起時，與響度相關本來就高；只有機台穩定運轉時才拿來看自動增益）==")
    for name, a in R["level_difference"].items():
        print(f"  {name}：中位數 {a['median_db']} dB（5–95% {a['p5_p95_db']}），與響度相關 {a['corr_with_level']}")
    for name, p in R["phase"].items():
        print(f"  相位 {name}：相干度 ≥ 0.5 的頻率比例 {p['frac_bins_coherence_ge_0p5']}，"
              f"相位斜率殘餘時間差 {p['residual_delay_from_phase_slope_us']} µs")


def cmd_chirp(args):
    out = Path(args.out)
    if inside_repo(out):
        raise SystemExit("輸出不可放在 Git 儲存庫內，請改到儲存庫外的資料夾")
    out.parent.mkdir(parents=True, exist_ok=True)
    dur = write_chirp(out)
    print(f"已寫入 {out}（{dur:.1f} 秒，48 kHz）。錄音開始後播一次、停止前播一次；播放裝置放在三支手機中間附近，音量開大但不破音。")


def cmd_run(args):
    out = Path(args.out)
    if inside_repo(out):
        raise SystemExit("輸出不可放在 Git 儲存庫內，請改到儲存庫外的資料夾")
    stereo = getattr(args, "stereo_ab", None)
    spacing = getattr(args, "ab_spacing_m", None)
    if stereo and (args.a or args.b):
        raise SystemExit("--stereo-ab 已經提供 A（左）與 B（右），不要再給 --a 或 --b")
    if not stereo and not (args.a and args.b):
        raise SystemExit("請給 --a 與 --b，或用 --stereo-ab 給一個雙聲道檔")
    if spacing is not None and not stereo:
        raise SystemExit("--ab-spacing-m 只用在 --stereo-ab（同一時鐘的兩軌）")
    if spacing is not None and not spacing > 0:
        raise SystemExit("--ab-spacing-m 必須是正數（公尺）")
    srcs = {"A": stereo or args.a, "B": stereo or args.b, "C": args.c}
    srcs = {k: Path(v) for k, v in srcs.items() if v}
    for k, p in srcs.items():
        if not p.is_file():
            raise SystemExit(f"找不到聲源 {k} 的檔案：{p}")
    (out / "input").mkdir(parents=True, exist_ok=True)
    wavs = {k: out / "input" / f"{k}.wav" for k in srcs}
    if stereo:
        decode_stereo(srcs["A"], wavs["A"], wavs["B"])
        if "C" in srcs:
            decode(srcs["C"], wavs["C"])
    else:
        for k, p in srcs.items():
            decode(p, wavs[k])
    import analyze_multi_mic as amm
    J = amm.run({k: str(v) for k, v in wavs.items()}, str(out), args.note,
                same_clock=("B",) if stereo else (),
                spacing_m={"B": spacing} if stereo and spacing is not None else None,
                temperature_c=getattr(args, "temperature_c", 20.0))
    R = report(J)
    R["sources"] = {k: p.name for k, p in srcs.items()}
    if stereo:
        R["sources"]["A"] += "（左聲道）"
        R["sources"]["B"] += "（右聲道）"
    with open(out / "offline_report.json", "w", encoding="utf-8") as fh:
        json.dump(R, fh, ensure_ascii=False, indent=2)
    print_report(R)
    print(f"\n圖與完整數字：{out}（fig1_sync.png、fig2_phase_*.png、fig3/fig4、summary.json、offline_report.json）")
    return R


def main(argv=None):
    ap = argparse.ArgumentParser(description="三手機錄音離線分析")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("chirp", help="產生同步嗶聲 wav")
    c.add_argument("--out", required=True)
    r = sub.add_parser("run", help="解碼並分析 2–3 個錄音檔")
    r.add_argument("--a", default=None, help="聲源 A（主控手機）")
    r.add_argument("--b", default=None, help="聲源 B")
    r.add_argument("--c", default=None, help="聲源 C（可省略；與 --stereo-ab 併用時是獨立時鐘的第三支麥克風）")
    r.add_argument("--stereo-ab", default=None,
                   help="雙聲道檔：左聲道當 A、右聲道當 B，兩軌同一時鐘，不對齊（例如 miniDSP EARS）")
    r.add_argument("--ab-spacing-m", type=float, default=None, help="A、B 兩支麥克風開孔的間距（公尺），用來檢查物理上限")
    r.add_argument("--temperature-c", type=float, default=20.0, help="現場氣溫（°C），用來算音速")
    r.add_argument("--out", required=True, help="輸出資料夾（儲存庫外）")
    r.add_argument("--note", default="", help="這場錄音的說明，例如機台、轉速、麥克風位置")
    args = ap.parse_args(argv)
    return cmd_chirp(args) if args.cmd == "chirp" else cmd_run(args)


if __name__ == "__main__":
    main()
