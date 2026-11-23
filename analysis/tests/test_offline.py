"""offline.py 測試：嗶聲檔、混合格式解碼、對齊判定、拒絕寫進儲存庫。

執行（不需要 pytest）：
  python -X utf8 analysis/tests/test_offline.py
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import offline  # noqa: E402
import test_synthetic as ts  # noqa: E402
from sync_chirp import detect_chirps  # noqa: E402


def _encode(rec, d, fmt):
    """把合成錄音存成手機可能給的格式：A＝網站 webm/opus、B＝錄音 App m4a/aac、C＝44.1 kHz wav。"""
    ff = offline.ffmpeg_exe()
    paths = {}
    for k, y in rec.items():
        raw = Path(d) / f"{k}_raw.wav"
        sf.write(raw, y.astype(np.float32), ts.SR, subtype="FLOAT")
        if fmt[k] == "webm":
            dst, extra = Path(d) / f"{k}.webm", ["-c:a", "libopus", "-b:a", "128k"]
        elif fmt[k] == "m4a":
            dst, extra = Path(d) / f"{k}.m4a", ["-c:a", "aac", "-b:a", "192k"]
        else:
            dst, extra = Path(d) / f"{k}.wav", ["-ar", "44100", "-c:a", "pcm_s16le"]
        subprocess.run([ff, "-hide_banner", "-loglevel", "error", "-y", "-i", str(raw), *extra, str(dst)],
                       check=True, timeout=120)
        paths[k] = dst
    return paths


def test_chirp_file_is_detected_once_at_pad():
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "chirp.wav"
        offline.cmd_chirp(type("A", (), {"out": str(out)}))
        y, sr = sf.read(out)
        assert sr == 48000 and abs(len(y) / sr - 1.5) < 1e-6, (sr, len(y))
        assert np.max(np.abs(y)) < 0.81
        # 嵌進機台噪音再找：只能找到 1 個，起點在 0.5 s 的填白之後
        noise = 0.05 * np.random.default_rng(1).normal(0, 1, 5 * sr)
        x = noise.copy()
        x[sr:sr + len(y)] += 0.1 * y
        found = detect_chirps(x, sr)
        assert len(found) == 1 and abs(found[0][0] - 1.5) < 0.001, found


def _run(rec, fmt, note):
    with tempfile.TemporaryDirectory() as d:
        paths = _encode(rec, d, fmt)
        out = Path(d) / "out"
        args = type("A", (), {"a": str(paths["A"]), "b": str(paths["B"]), "c": str(paths["C"]),
                              "out": str(out), "note": note})
        R = offline.cmd_run(args)
        saved = json.loads((out / "offline_report.json").read_text(encoding="utf-8"))
        assert saved["alignment"] == R["alignment"]
        for f in ("fig1_sync.png", "fig2_phase_AB.png", "summary.json", "input/A.wav"):
            assert (out / f).exists(), f
        return R


def test_mixed_formats_with_chirps_are_verified():
    R = _run(ts.recordings(with_chirp=True), {"A": "webm", "B": "m4a", "C": "wav"}, "混合格式")
    assert R["alignment"]["verified"] is True, R["alignment"]
    assert R["alignment"]["channels"] == ["A", "B", "C"]
    assert R["sources"] == {"A": "A.webm", "B": "B.m4a", "C": "C.wav"}
    for k in ("B", "C"):
        p = R["pairs"][f"{k}_vs_A"]
        assert p["coarse_method"] == "chirp", p
        assert abs(p["drift_ppm"] - ts.CLOCK_PPM[k]) < 3, p
    assert all(len(v) == 2 for v in R["chirps_detected_s"].values()), R["chirps_detected_s"]
    # 合成增益 A 1.0、B 0.7、C 1.3：運轉段 A−B ≈ +3.1 dB、A−C ≈ −2.3 dB（中位數落在運轉段）
    assert abs(R["level_difference"]["level_diff_A_minus_B_db"]["median_db"] - 3.1) < 0.5, R["level_difference"]
    assert abs(R["level_difference"]["level_diff_A_minus_C_db"]["median_db"] + 2.3) < 0.5, R["level_difference"]
    assert "possible_agc" not in json.dumps(R)


def test_without_chirp_falls_back_to_envelope_and_still_verifies():
    R = _run(ts.recordings(with_chirp=False), {"A": "webm", "B": "webm", "C": "webm"}, "無嗶聲")
    assert R["alignment"]["verified"] is True, R["alignment"]
    for k in ("B", "C"):
        assert R["pairs"][f"{k}_vs_A"]["coarse_method"] == "envelope", R["pairs"]


def test_refuses_output_inside_repository():
    for cmd, extra in ((offline.cmd_chirp, {}), (offline.cmd_run, {"a": "x", "b": "y", "c": None, "note": ""})):
        args = type("A", (), {"out": str(offline.REPO / "analysis" / "out_should_not_exist"), **extra})
        try:
            cmd(args)
        except SystemExit as e:
            assert "儲存庫" in str(e), e
        else:
            raise AssertionError("應該拒絕")
        assert not (offline.REPO / "analysis" / "out_should_not_exist").exists()


def test_missing_input_file_is_reported():
    with tempfile.TemporaryDirectory() as d:
        args = type("A", (), {"a": str(Path(d) / "nope.webm"), "b": str(Path(d) / "nope2.webm"), "c": None,
                              "out": str(Path(d) / "out"), "note": ""})
        try:
            offline.cmd_run(args)
        except SystemExit as e:
            assert "找不到聲源 A" in str(e), e
        else:
            raise AssertionError("應該報錯")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL {t.__name__}: {e!r}")
    print(f"{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
