"""record_usb.py — 同時錄一台雙聲道 USB 裝置（例如 miniDSP EARS）與一支單聲道 USB 麥克風（例如 UMIK-2）。

Windows 內建錄音程式一次只能錄一個裝置。本程式用 ffmpeg（DirectShow）在同一個程序裡同時開兩個輸入，
各存一個 wav。兩台裝置各有自己的時鐘，起點差與漂移交給 analysis/offline.py 處理。

  python -X utf8 analysis/record_usb.py list
  python -X utf8 analysis/record_usb.py record --stereo EARS --mono UMIK --seconds 60 --out D:/cnc_offline/run2
  python -X utf8 analysis/offline.py run --stereo-ab D:/cnc_offline/run2/stereo.wav --c D:/cnc_offline/run2/mono.wav --out D:/cnc_offline/run2/analysis

錄音前請在 Windows「音效 → 錄製 → 內容」把兩台裝置都設成 48000 Hz，並關閉「音訊增強」。
EARS 的左右增益（DIP 開關）要相同，錄音期間不要改。
錄音檔不可放進 Git 儲存庫（本程式會拒絕）。只支援 Windows。
"""
import argparse
import datetime
import json
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from offline import ffmpeg_exe, inside_repo  # noqa: E402

SR = 48000
_AUDIO_LINE = re.compile(r'"(.+)"\s+\(audio\)')


def parse_devices(text):
    """從 `ffmpeg -list_devices true -f dshow -i dummy` 的輸出取出音訊輸入裝置名稱（保留順序、去重複）。"""
    out = []
    for line in text.splitlines():
        m = _AUDIO_LINE.search(line)
        if m and m.group(1) not in out:
            out.append(m.group(1))
    return out


def list_devices():
    if sys.platform != "win32":
        raise SystemExit("本程式用 DirectShow，只支援 Windows")
    p = subprocess.run([ffmpeg_exe(), "-hide_banner", "-list_devices", "true", "-f", "dshow", "-i", "dummy"],
                       capture_output=True, encoding="utf-8", errors="replace", timeout=60)
    return parse_devices(p.stderr)


def pick(devices, needle, role):
    """用名稱片段（不分大小寫）選裝置；必須剛好一台符合。"""
    hits = [d for d in devices if needle.lower() in d.lower()]
    if len(hits) != 1:
        listing = "\n".join(f"  - {d}" for d in devices) or "  （沒有找到任何音訊輸入裝置）"
        why = "找不到" if not hits else f"有 {len(hits)} 台符合"
        raise SystemExit(f"{role}裝置「{needle}」{why}。目前的輸入裝置：\n{listing}")
    return hits[0]


def build_cmd(ffmpeg, inputs, seconds, bits, sr=SR):
    """inputs: [(裝置名稱, 聲道數, 輸出路徑), ...]。同一個 ffmpeg 程序同時開所有輸入。"""
    codec = {16: "pcm_s16le", 24: "pcm_s24le"}[bits]
    cmd = [ffmpeg, "-hide_banner", "-loglevel", "warning", "-y"]
    for name, channels, _ in inputs:
        cmd += ["-f", "dshow", "-sample_rate", str(sr), "-channels", str(channels), "-sample_size", str(bits),
                "-audio_buffer_size", "50", "-i", f"audio={name}"]
    for i, (_, channels, path) in enumerate(inputs):
        cmd += ["-map", f"{i}:a", "-t", f"{seconds:g}", "-ac", str(channels), "-ar", str(sr), "-c:a", codec, str(path)]
    return cmd


def check_file(path, channels, seconds, sr=SR):
    """錄完後檢查：聲道數、取樣率、長度、是否破音或沒聲音、雙聲道是否其實是單聲道複製。回傳 (stats, problems)。"""
    y, got_sr = sf.read(str(path), dtype="float32", always_2d=True)
    problems = []
    if y.shape[1] != channels:
        problems.append(f"聲道數是 {y.shape[1]}，預期 {channels}")
    if got_sr != sr:
        problems.append(f"取樣率是 {got_sr}，預期 {sr}")
    dur = len(y) / got_sr
    if dur < 0.9 * seconds:
        problems.append(f"只錄到 {dur:.1f} 秒，預期 {seconds:g} 秒")
    per = []
    for i in range(y.shape[1]):
        peak = float(np.max(np.abs(y[:, i]))) if len(y) else 0.0
        rms_db = float(20 * np.log10(np.std(y[:, i]) + 1e-12)) if len(y) else -240.0
        per.append({"peak": round(peak, 4), "rms_dbfs": round(rms_db, 1)})
        if peak >= 0.999:
            problems.append(f"第 {i + 1} 聲道破音（峰值到滿刻度），請調低增益")
        if rms_db < -80:
            problems.append(f"第 {i + 1} 聲道幾乎沒有聲音（{rms_db:.0f} dBFS）")
    if y.shape[1] == 2 and len(y) and np.max(np.abs(y[:, 0] - y[:, 1])) < 1e-6:
        problems.append("左右兩軌完全相同：錄到的是單聲道複製成雙聲道，請檢查 Windows 輸入格式是否為 2 聲道")
    return {"file": Path(path).name, "channels": int(y.shape[1]), "sample_rate": int(got_sr),
            "duration_s": round(dur, 3), "per_channel": per}, problems


def _run_ffmpeg(cmd, seconds):
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8", errors="replace")
    try:
        _, err = p.communicate(timeout=seconds + 60)
    except KeyboardInterrupt:
        _, err = p.communicate("q", timeout=30)       # 提早結束：請 ffmpeg 收尾，檔案仍然完整
    except subprocess.TimeoutExpired:
        p.kill()
        _, err = p.communicate()
        raise SystemExit("錄音超過預期時間仍未結束，已中止")
    return p.returncode, err or ""


def cmd_list(_args):
    devices = list_devices()
    if not devices:
        print("沒有找到任何音訊輸入裝置。請確認 USB 已接上，且 Windows 隱私權設定允許桌面應用程式使用麥克風。")
        return devices
    print("音訊輸入裝置（--stereo／--mono 給名稱的一部分即可）：")
    for d in devices:
        print(f"  - {d}")
    return devices


def cmd_record(args):
    out = Path(args.out)
    if inside_repo(out):
        raise SystemExit("輸出不可放在 Git 儲存庫內，請改到儲存庫外的資料夾")
    if not args.seconds > 0:
        raise SystemExit("--seconds 必須是正數")
    devices = list_devices()
    stereo = pick(devices, args.stereo, "雙聲道")
    mono = pick(devices, args.mono, "單聲道") if args.mono else None
    if mono == stereo:
        raise SystemExit("--stereo 與 --mono 選到同一台裝置，請給更明確的名稱")
    out.mkdir(parents=True, exist_ok=True)
    inputs = [(stereo, 2, out / "stereo.wav")] + ([(mono, 1, out / "mono.wav")] if mono else [])
    ffmpeg = ffmpeg_exe()
    print(f"開始錄音 {args.seconds:g} 秒（Ctrl+C 可提早結束）：{stereo}" + (f" ＋ {mono}" if mono else ""))
    used_bits, tried = None, []
    for bits in ([args.bits, 16] if args.bits != 16 else [16]):
        started = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="milliseconds")
        code, err = _run_ffmpeg(build_cmd(ffmpeg, inputs, args.seconds, bits), args.seconds)
        tried.append({"bits": bits, "returncode": code, "stderr_tail": err[-600:]})
        if code == 0 and all(p.exists() and p.stat().st_size > 1000 for _, _, p in inputs):
            used_bits = bits
            break
        print(f"  {bits} 位元開啟失敗，改試下一種格式")
    if used_bits is None:
        raise SystemExit("錄音失敗。ffmpeg 訊息：\n" + tried[-1]["stderr_tail"])
    files, problems = [], []
    for name, channels, path in inputs:
        st, pr = check_file(path, channels, args.seconds)
        st["device"] = name
        files.append(st)
        problems += [f"{path.name}：{x}" for x in pr]
    meta = {"started_at_utc": started, "requested_seconds": args.seconds, "sample_rate": SR, "bits": used_bits,
            "files": files, "problems": problems, "note": args.note,
            "attempts": [{"bits": t["bits"], "returncode": t["returncode"]} for t in tried]}
    with open(out / "recording.json", "w", encoding="utf-8") as fh:
        json.dump(meta, fh, ensure_ascii=False, indent=2)
    for st in files:
        ch = "、".join(f"峰值 {c['peak']}／{c['rms_dbfs']} dBFS" for c in st["per_channel"])
        print(f"  {st['file']}：{st['channels']} 聲道、{st['sample_rate']} Hz、{st['duration_s']} 秒、{used_bits} 位元；{ch}")
    if problems:
        print("需要處理的問題：")
        for x in problems:
            print(f"  - {x}")
    else:
        print("檢查通過。下一步：")
        c_arg = f' --c "{out / "mono.wav"}"' if mono else ""
        print(f'  python -X utf8 analysis/offline.py run --stereo-ab "{out / "stereo.wav"}"{c_arg} '
              f'--ab-spacing-m <左右麥克風間距，公尺> --out "{out / "analysis"}"')
    return meta


def main(argv=None):
    ap = argparse.ArgumentParser(description="同時錄雙聲道 USB 裝置與單聲道 USB 麥克風（Windows）")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="列出音訊輸入裝置")
    r = sub.add_parser("record", help="錄音")
    r.add_argument("--stereo", required=True, help="雙聲道裝置名稱的一部分，例如 EARS")
    r.add_argument("--mono", default=None, help="單聲道裝置名稱的一部分，例如 UMIK（可省略）")
    r.add_argument("--seconds", type=float, required=True)
    r.add_argument("--out", required=True, help="輸出資料夾（儲存庫外）")
    r.add_argument("--bits", type=int, choices=(16, 24), default=24, help="位元深度；裝置不支援 24 時自動改用 16")
    r.add_argument("--note", default="", help="這場錄音的說明：機台、工況、麥克風位置與間距")
    args = ap.parse_args(argv)
    if args.cmd == "list":
        return cmd_list(args)
    meta = cmd_record(args)
    if meta["problems"]:
        raise SystemExit(1)       # 檔案已存下，但有需要處理的問題（破音、沒聲音、聲道不對）
    return meta


if __name__ == "__main__":
    main()
