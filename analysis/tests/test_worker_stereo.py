"""地端 worker 遇到雙聲道裝置（例如 miniDSP EARS）時要保留左右兩軌，不可以混成單聲道。

執行（不需要 pytest）：
  python -X utf8 analysis/tests/test_worker_stereo.py
資料庫整合測試另外需要（和 test_worker.py 相同）：
  $env:WORKER_TEST_ADMIN_URL = 'postgresql://postgres@127.0.0.1:55433/postgres'
沒有設定時只跑不需要資料庫的部分，並在最後說明略過了幾項。

規則
- 整場錄音只有一台雙聲道裝置、而且拆開後不超過 3 軌：左聲道＝A、右聲道＝B（與 A 同一時鐘，不對齊），
  另一台單聲道裝置＝C。網站上的位置代號（A、B）和模型的軌道代號不一定相同，對照寫在 summary.track_sources。
- 其他情況（兩台以上雙聲道、或拆開後超過 3 軌）：照舊，每台裝置混成一軌，並在 summary.stereo 標明。
- 左右兩軌內容完全相同的「雙聲道」檔是單聲道複製出來的，當成單聲道。
- 拆開後獨立麥克風對不上左聲道（精對齊失敗）時，退回每台裝置一軌再算一次，並在 summary.stereo 寫明原因。
- 只有一台單聲道裝置：照舊判定為不支援。
"""
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
import soundfile as sf

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

import worker  # noqa: E402
import test_synthetic as ts  # noqa: E402
import test_ears_umik as te  # noqa: E402

ADMIN = os.environ.get("WORKER_TEST_ADMIN_URL")
needs_db = []


def db(fn):
    needs_db.append(fn.__name__)
    return fn


def track(source, channel):
    return {"source": source, "channel": channel}


def encode(samples, path):
    """float 陣列（單聲道或 [n, 2]）→ Opus webm，和瀏覽器上傳的格式相同。"""
    wav = Path(path).with_suffix(".wav")
    sf.write(wav, np.asarray(samples, dtype="float32"), ts.SR, subtype="FLOAT")
    subprocess.run([worker.ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y", "-i", str(wav),
                    "-c:a", "libopus", "-b:a", "128k", str(path)], check=True, timeout=120)
    return Path(path).read_bytes()


_SCENE = {}


def scene():
    """A、B 同一時鐘（B 的機台聲晚 12 取樣點），C 是獨立時鐘（快 25 ppm）。回傳各種編碼好的 webm。"""
    if not _SCENE:
        with te.ears_scene() as rec, tempfile.TemporaryDirectory() as d:
            n = min(len(rec["A"]), len(rec["B"]))
            left, right = rec["A"][:n], rec["B"][:n]
            _SCENE.update(
                stereo=encode(np.stack([left, right], axis=1), Path(d) / "stereo.webm"),
                fake_stereo=encode(np.stack([left, left], axis=1), Path(d) / "fake.webm"),
                mono=encode(rec["C"], Path(d) / "mono.webm"),
                left=left, right=right)
    return _SCENE


# ---------- 不需要資料庫 ----------

def test_plan_keeps_mono_layouts_as_before():
    p = worker.plan_tracks({"A": 1, "B": 1})
    assert p == {"mode": "none", "tracks": {"A": track("A", "Mono"), "B": track("B", "Mono")}, "same_clock": []}, p
    p = worker.plan_tracks({"A": 1, "B": 1, "C": 1})
    assert p["mode"] == "none" and p["same_clock"] == [] and list(p["tracks"]) == ["A", "B", "C"], p
    assert all(p["tracks"][k] == track(k, "Mono") for k in "ABC"), p


def test_plan_splits_the_only_stereo_device_into_a_and_b():
    for channels, mono_source, stereo_source in (({"A": 1, "B": 2}, "A", "B"), ({"A": 2, "B": 1}, "B", "A")):
        p = worker.plan_tracks(channels)
        assert p == {"mode": "split", "same_clock": ["B"],
                     "tracks": {"A": track(stereo_source, "Left"), "B": track(stereo_source, "Right"),
                                "C": track(mono_source, "Mono")}}, p
    p = worker.plan_tracks({"A": 2})
    assert p == {"mode": "split", "same_clock": ["B"], "tracks": {"A": track("A", "Left"), "B": track("A", "Right")}}, p


def test_plan_downmixes_when_split_would_not_fit_three_tracks():
    for channels in ({"A": 2, "B": 2}, {"A": 2, "B": 1, "C": 1}, {"A": 1, "B": 2, "C": 2}):
        p = worker.plan_tracks(channels)
        assert p["mode"] == "downmixed" and p["same_clock"] == [] and list(p["tracks"]) == sorted(channels), p
        for k, n in channels.items():
            assert p["tracks"][k] == track(k, "Mix" if n == 2 else "Mono"), p


def test_plan_rejects_a_single_mono_device_and_unknown_layouts():
    for channels in ({"A": 1}, {"B": 1, "C": 1}, {"A": 1, "B": 1, "C": 1, "D": 1}, {}):
        try:
            worker.plan_tracks(channels)
        except worker.UnsupportedLayout as e:
            assert "同步模型僅支援" in str(e), str(e)
        else:
            raise AssertionError(f"應判定為不支援：{channels}")


def test_decode_keeps_two_channels_and_detects_copied_mono():
    s = scene()
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        for name, expected in (("stereo", 2), ("fake_stereo", 1), ("mono", 1)):
            (d / f"{name}.webm").write_bytes(s[name])
            assert worker.decode_native(d / f"{name}.webm", d / f"{name}.wav") == expected, name
        native, _ = sf.read(d / "stereo.wav", dtype="float32", always_2d=True)
        assert native.shape[1] == 2
        plan = worker.plan_tracks({"A": 1, "B": 2})
        out = worker.write_tracks({"A": d / "mono.wav", "B": d / "stereo.wav"}, plan, d / "tracks")
        assert sorted(out) == ["A", "B", "C"], out
        got = {k: sf.read(out[k], dtype="float32", always_2d=True)[0] for k in out}
        assert all(v.shape[1] == 1 for v in got.values()), {k: v.shape for k, v in got.items()}
        assert np.array_equal(got["A"][:, 0], native[:, 0]) and np.array_equal(got["B"][:, 0], native[:, 1])
        assert not np.array_equal(got["A"], got["B"])
        mix = worker.write_tracks({"A": d / "mono.wav", "B": d / "stereo.wav"},
                                  {"mode": "downmixed", "same_clock": [],
                                   "tracks": {"A": track("A", "Mono"), "B": track("B", "Mix")}}, d / "mix")
        mixed = sf.read(mix["B"], dtype="float32", always_2d=True)[0][:, 0]
        assert np.allclose(mixed, native.mean(axis=1), atol=1e-6)


# ---------- 需要資料庫 ----------

def _run_one(tracks, analyzer=None):
    import psycopg
    import test_worker as tw
    saved = worker.ANALYZER
    try:
        if analyzer is not None:
            worker.ANALYZER = analyzer
        with tw.fresh_db() as (admin, role), tempfile.TemporaryDirectory() as work:
            tw.seed_session(admin, tracks)
            ok = worker.run_once(role, "stereo-test", work, 60, 900, "testcommit")
            job = tw.jobs(admin)[0]
            with psycopg.connect(admin) as c:
                row = c.execute("SELECT result FROM mobile_capture.analysis_results").fetchone()
                align = c.execute("SELECT status FROM mobile_capture.audio_alignment_runs").fetchone()
            return ok, job, (row[0] if row else None), (align[0] if align else None)
    finally:
        worker.ANALYZER = saved


@db
def test_stereo_device_plus_mono_device_is_analysed_as_three_tracks():
    s = scene()
    ok, job, result, align = _run_one({"A": s["mono"], "B": s["stereo"]})
    assert ok is True and job[0] == "completed" and job[1] == 1, job
    summary = result["summary"]
    assert summary["channels"] == ["A", "B", "C"], summary["channels"]
    assert summary["same_clock"] == ["B"], summary.get("same_clock")
    assert summary["track_sources"] == {"A": track("B", "Left"), "B": track("B", "Right"), "C": track("A", "Mono")}
    assert summary["stereo"]["mode"] == "split" and summary["stereo"]["source"] == "B", summary["stereo"]
    b, c = summary["sync"]["B_vs_A"], summary["sync"]["C_vs_A"]
    assert b["same_clock"] is True and b["aligned"] is False, b
    assert abs(b["acoustic_tdoa_samples"] - te.TDOA_SAMPLES) < 1.5, b["acoustic_tdoa_samples"]   # 左右之間的時間差要保留
    assert abs(c["drift_ppm"] - 25) < 3, c["drift_ppm"]
    assert result["alignment"]["verified"] is True and result["alignment"]["same_clock_pairs"] == ["B_vs_A"], result["alignment"]
    assert result["alignment"]["channels"] == ["A", "B", "C"] and align == "verified"
    assert set(summary["phase"]) == {"A-B", "A-C", "B-C"}, list(summary["phase"])


@db
def test_single_stereo_device_is_analysed_as_a_same_clock_pair():
    ok, job, result, align = _run_one({"A": scene()["stereo"]})
    assert ok is True and job[0] == "completed", job
    summary = result["summary"]
    assert summary["channels"] == ["A", "B"] and summary["same_clock"] == ["B"], summary
    assert summary["track_sources"] == {"A": track("A", "Left"), "B": track("A", "Right")}
    assert result["alignment"]["verified"] is True and align == "verified", result["alignment"]


@db
def test_single_mono_device_is_still_unsupported():
    ok, job, result, _ = _run_one({"A": scene()["mono"]})
    assert ok is False and job[0] == "failed" and job[1] == 1 and "同步模型僅支援" in job[2], job
    assert result is None


@db
def test_copied_mono_stereo_file_is_treated_as_mono():
    s = scene()
    ok, job, result, _ = _run_one({"A": s["mono"], "B": s["fake_stereo"]})
    assert ok is True and job[0] == "completed", job
    summary = result["summary"]
    assert summary["channels"] == ["A", "B"] and "same_clock" not in summary, summary.get("same_clock")
    assert summary["track_sources"] == {"A": track("A", "Mono"), "B": track("B", "Mono")}, summary["track_sources"]
    assert summary["stereo"]["mode"] == "none", summary["stereo"]


@db
def test_falls_back_to_one_track_per_device_when_split_cannot_be_aligned():
    """模型在拆開的三軌上精對齊失敗時，退回每台裝置一軌重算；用替身分析程式固定這個情況。"""
    s = scene()
    with tempfile.TemporaryDirectory() as d:
        fake = Path(d) / "fake_analyzer.py"
        fake.write_text(
            "import json, os, sys\n"
            "a = sys.argv\n"
            "if '--same-clock' in a:\n"
            "    sys.stderr.write('Traceback (most recent call last):\\n')\n"
            "    sys.stderr.write('RuntimeError: 精對齊失敗：峰值清楚的窗只有 0 個（共 51）\\n')\n"
            "    sys.exit(1)\n"
            "out = a[a.index('--out') + 1]\n"
            "os.makedirs(out, exist_ok=True)\n"
            "ch = ['A', 'B'] + (['C'] if '--c' in a else [])\n"
            "J = {'channels': ch, 'sync': {k + '_vs_A': {'after_alignment': {'fine_offset_samples': 0.1, 'drift_ppm': 0.2}}\n"
            "                              for k in ch[1:]}}\n"
            "json.dump(J, open(os.path.join(out, 'summary.json'), 'w', encoding='utf-8'))\n", encoding="utf-8")
        ok, job, result, align = _run_one({"A": s["mono"], "B": s["stereo"]}, analyzer=fake)
    assert ok is True and job[0] == "completed" and job[1] == 1, job
    summary = result["summary"]
    assert summary["channels"] == ["A", "B"], summary["channels"]
    assert summary["track_sources"] == {"A": track("A", "Mono"), "B": track("B", "Mix")}, summary["track_sources"]
    assert summary["stereo"]["mode"] == "downmixed" and summary["stereo"]["source"] == "B", summary["stereo"]
    assert "精對齊失敗" in summary["stereo"]["reason"], summary["stereo"]
    assert result["alignment"]["verified"] is True and align == "verified"


if __name__ == "__main__":
    tests = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    failed = skipped = 0
    for fn in tests:
        if fn.__name__ in needs_db and not ADMIN:
            skipped += 1
            print(f"SKIP {fn.__name__}（沒有設定 WORKER_TEST_ADMIN_URL）")
            continue
        t0 = time.time()
        try:
            fn()
            print(f"PASS {fn.__name__} ({time.time() - t0:.1f}s)")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL {fn.__name__}: {type(e).__name__}: {str(e)[:400]}")
    print(f"{len(tests) - failed - skipped}/{len(tests)} passed" + (f"，略過 {skipped} 項" if skipped else ""))
    sys.exit(1 if failed else 0)
