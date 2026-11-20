"""background_check.py 測試：合成資料，答案已知。

執行（不需要 pytest，也不需要接上裝置）：
  python -X utf8 analysis/tests/test_background.py
"""
import json
import os
import sys
import tempfile
from pathlib import Path

import numpy as np
import scipy.signal as ss
import soundfile as sf

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import background_check as bc  # noqa: E402
import offline  # noqa: E402

SR = 48000
RNG = np.random.default_rng(20261120)


def white(sec):
    return RNG.normal(0, 1, int(sec * SR))


def room(x, delay, seed):
    """模擬「聲源 → 麥克風」：延遲加上幾個衰減的反射。"""
    r = np.random.default_rng(seed)
    h = np.zeros(800)
    h[delay] = 1.0
    for _ in range(6):
        h[delay + r.integers(20, 500)] += r.uniform(-0.4, 0.4)
    return ss.fftconvolve(x, h, mode="full")[:len(x)]


def band(rows, name):
    return next(r for r in rows if r["band_hz"] == name)


def test_same_source_through_two_paths_is_cancelled():
    s = white(40)
    a, b = room(s, 30, 1), 0.6 * room(s, 55, 2)
    res, _ = bc.analyse(a + 1e-3 * white(40), b + 1e-3 * white(40), SR)
    for r in res["bands"]:
        assert r["coherence_median"] > 0.98, r
        # 反射路徑的反濾波需要很長的濾波器，所以不是無限深；−14 dB 以下就算確實消掉
        assert r["achieved_db_predict_b"] < -14 and r["achieved_db_predict_a"] < -14, r
        assert bc.verdict_text(r) == "有效"
    assert res["overall_achieved_db"]["predict_b"] < -15 and res["overall_achieved_db"]["predict_a"] < -15


def test_unrelated_noise_is_not_cancelled_and_not_made_louder():
    res, _ = bc.analyse(white(40), white(40), SR)
    for r in res["bands"]:
        assert r["coherence_median"] < 0.05, r
        assert -0.7 < r["achieved_db_predict_b"] < 0.7 and -0.7 < r["achieved_db_predict_a"] < 0.7, r
        assert r["limit_db_predict_b"] > -0.5, r
        assert bc.verdict_text(r) == "效果很小"


def test_partial_coherence_matches_theory():
    """共同聲源加上各自獨立的噪音（功率為共同聲源的 1/9）：γ² = 1/(1+1/9)² = 0.81，上限 10·log10(1−0.81) = −7.2 dB。"""
    s = white(60)
    a, b = s + white(60) / 3, s + white(60) / 3
    res, _ = bc.analyse(a, b, SR)
    for r in res["bands"]:
        assert abs(r["coherence_median"] - 0.81) < 0.04, r
        assert abs(r["limit_db_predict_b"] + 7.2) < 0.6, r
        # 實際做到不可能比上限好很多，也不該差太多（訊號是平穩的）
        assert r["limit_db_predict_b"] - 0.8 < r["achieved_db_predict_b"] < r["limit_db_predict_b"] + 1.5, r
        assert bc.verdict_text(r) == "部分有效"


def test_band_dependent_coherence():
    """1 kHz 以下是共同聲源，以上各自獨立：低頻有效、高頻無效。"""
    lo = ss.sosfilt(ss.butter(8, 800, btype="low", fs=SR, output="sos"), white(40))
    hp = ss.butter(8, 1800, btype="high", fs=SR, output="sos")
    a = room(lo, 20, 3) + 0.3 * ss.sosfilt(hp, white(40))
    b = room(lo, 45, 4) + 0.3 * ss.sosfilt(hp, white(40))
    res, _ = bc.analyse(a, b, SR)
    assert band(res["bands"], "200-400")["achieved_db_predict_b"] < -15, band(res["bands"], "200-400")
    assert bc.verdict_text(band(res["bands"], "200-400")) == "有效"
    hi = band(res["bands"], "3150-6300")
    assert hi["achieved_db_predict_b"] > -1 and bc.verdict_text(hi) == "效果很小", hi


def test_moving_source_is_judged_on_unseen_half():
    """背景聲源在錄音中途換位置：前半段學到的轉移函數套不上後半段，實際做到要反映出來。"""
    s = white(40)
    k = len(s) // 2
    a = room(s, 30, 5)
    b = np.concatenate([room(s, 40, 6)[:k], room(s, 140, 7)[k:]])
    res, _ = bc.analyse(a, b, SR)
    r = band(res["bands"], "800-1600")
    assert r["achieved_db_predict_b"] > -3, r                 # 換位置後幾乎消不掉
    still = bc.analyse(a, room(s, 40, 6), SR)[0]
    assert band(still["bands"], "800-1600")["achieved_db_predict_b"] < -14


def test_input_validation_and_outputs():
    try:
        bc.analyse(white(5), white(5), SR)
    except ValueError as e:
        assert "至少需要" in str(e), e
    else:
        raise AssertionError("太短的錄音應該拒絕")
    args = lambda **kw: type("A", (), {"note": "", **kw})  # noqa: E731
    try:
        bc.cmd(args(stereo="x.wav", out=str(offline.REPO / "analysis" / "bg_should_not_exist")))
    except SystemExit as e:
        assert "儲存庫" in str(e), e
    else:
        raise AssertionError("應該拒絕寫進儲存庫")
    assert not (offline.REPO / "analysis" / "bg_should_not_exist").exists()
    with tempfile.TemporaryDirectory() as d:
        mono = Path(d) / "mono.wav"
        sf.write(mono, 0.1 * white(25), SR)
        try:
            bc.cmd(args(stereo=str(mono), out=str(Path(d) / "o1")))
        except SystemExit as e:
            assert "不是雙聲道" in str(e), e
        else:
            raise AssertionError("單聲道檔應該拒絕")
        s = 0.1 * white(30)
        clip = Path(d) / "stereo.wav"
        sf.write(clip, np.stack([room(s, 10, 8), 0.8 * room(s, 25, 9)], 1), SR, subtype="PCM_16")
        res = bc.cmd(args(stereo=str(clip), out=str(Path(d) / "o2")))
        saved = json.loads((Path(d) / "o2" / "background_check.json").read_text(encoding="utf-8"))
        assert saved["bands"] == res["bands"] and saved["source"] == "stereo.wav"
        assert (Path(d) / "o2" / "background_check.png").stat().st_size > 10000
        assert res["clipped"] is False and len(res["bands"]) == len(bc.BANDS)


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
