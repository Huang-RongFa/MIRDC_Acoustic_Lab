"""把地端的數值核心和網站內建分析（backend/analysis_signal.py）逐項比對。

網站的原始碼不放進這個儲存庫，所以要用環境變數指出它在本機的位置；沒有設定就整支跳過：
  $env:SITE_ANALYSIS_SIGNAL_PY = 'D:/site/backend/analysis_signal.py'
  python -X utf8 analysis/tests/test_track_reference.py

比對的是同一段已解碼的樣本進去之後，兩邊算出來的數字。解碼本身不在這裡比（網站用 PyAV，地端用 ffmpeg 指令）。
"""
import hashlib
import importlib.util
import os
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from track_analysis import signal_contract as sc  # noqa: E402

REF_PATH = os.environ.get("SITE_ANALYSIS_SIGNAL_PY")
RNG = np.random.default_rng(20261120)
# 地端把 spectrogram／mfcc 存成 float32；網站是 float64。這兩個容許值就是 float32 在該數值範圍的進位誤差
SPEC_TOL_DB = 2e-5          # 數值範圍 -120..0
MFCC_TOL = 2e-4             # C0 可到 -1000 左右


def load_reference():
    spec = importlib.util.spec_from_file_location("site_analysis_signal", REF_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def signals(sr, seconds=3.0):
    n = int(sr * seconds)
    t = np.arange(n) / sr
    return {
        "white": 0.2 * RNG.normal(size=n),
        "tone": 0.5 * np.sin(2 * np.pi * 997.0 * t),
        "sweep": 0.3 * np.sin(2 * np.pi * (200 + 3000 * t) * t),
        "silence": np.zeros(n),
        "quiet": 1e-7 * RNG.normal(size=n),             # 落在 -120 dBFS 下限附近
    }


INTERVALS = [(0.0, None), (1.0, 2.0), (0.3337, 1.77777), (0.0, 0.05), (2.5, 99.0), (2.99, None), (5.0, None), (1e-9, 1.0)]


def test_resampler_is_identical():
    ref = load_reference()
    for sr in (48000, 44100, 16000, 22050, 32000, 96000, 11025):
        x = RNG.normal(size=sr + 77)
        mine, theirs = sc.resample_to_analysis(x, sr), ref.resample(x, sr)
        assert mine.shape == theirs.shape and np.array_equal(mine, theirs), (sr, mine.shape, theirs.shape)


def test_mel_filterbank_matches():
    ref = load_reference()
    assert np.abs(sc.mel_filterbank() - ref.mel_filters()).max() < 1e-12


def test_full_precision_amplitude_path_matches():
    """float64 的中間結果（還沒轉 float32）必須和網站幾乎逐位元相同。"""
    ref = load_reference()
    for name, x in signals(44100).items():
        theirs = ref.calculate(x, 44100)
        amp, _ = sc.stft_amplitude(x)
        assert np.abs(sc.spectrogram_db(amp) - theirs["spectrogram"]).max() < 1e-9, name
        assert np.abs(sc.mfcc_from_amplitude(amp) - theirs["mfcc"]).max() < 1e-8, name


def test_analyze_channel_matches_calculate():
    ref = load_reference()
    worst = {"spectrogram": 0.0, "mfcc": 0.0, "times": 0.0, "valid_range": 0.0}
    cases = no_data = 0
    for sr in (44100, 48000, 16000, 96000):
        for name, x in signals(sr).items():
            for start, end in INTERVALS:
                theirs = ref.calculate(x, sr, start, end)
                try:
                    mine = sc.analyze_channel(x, sr, start, end)
                except sc.NoData:
                    assert theirs is None, (sr, name, start, end)
                    no_data += 1
                    continue
                assert theirs is not None, (sr, name, start, end)
                cases += 1
                key = (sr, name, start, end)
                assert mine["spectrogram_db"].shape == theirs["spectrogram"].shape, key
                assert mine["mfcc"].shape == theirs["mfcc"].shape, key
                d = {"spectrogram": np.abs(mine["spectrogram_db"] - theirs["spectrogram"]).max(),
                     "mfcc": np.abs(mine["mfcc"] - theirs["mfcc"]).max(),
                     "times": np.abs(mine["times"] - theirs["times"]).max(),
                     "valid_range": np.abs(np.asarray(mine["valid_range"]) - np.asarray(theirs["valid_range"])).max()}
                assert d["spectrogram"] < SPEC_TOL_DB and d["mfcc"] < MFCC_TOL, (key, d)
                assert d["times"] == 0.0 and d["valid_range"] == 0.0, (key, d)
                worst = {k: max(worst[k], float(v)) for k, v in d.items()}
    assert cases > 60 and no_data > 10, (cases, no_data)
    print(f"    比對 {cases} 個有結果的案例、{no_data} 個資料不足的案例；最大差異 {worst}")


def test_matrix_keys_match():
    ref = load_reference()
    x = signals(44100)["white"]
    theirs = ref.calculate(x, 44100)
    assert sorted(theirs) == ["mfcc", "spectrogram", "times", "valid_range"]


if __name__ == "__main__":
    if not REF_PATH:
        print("略過：沒有設定 SITE_ANALYSIS_SIGNAL_PY（網站的 backend/analysis_signal.py 在本機的路徑）")
        sys.exit(0)
    print(f"參考實作 sha256 = {hashlib.sha256(Path(REF_PATH).read_bytes()).hexdigest()}")
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL {t.__name__}: {type(e).__name__}: {str(e)[:600]}")
    print(f"{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
