"""合成資料測試：已知偏移的三支麥克風＋同步嗶聲。

執行（不需要 pytest；有 pytest 也可以 `pytest analysis/tests`）：
  python -X utf8 analysis/tests/test_synthetic.py

合成情境
- 機台聲：刃頻 160 Hz 的 12 階諧波（各階帶慢速相位抖動）＋ 1–6 kHz 帶通的切削寬頻聲，前 3 秒停機。
- 三支麥克風各自有：不同聲學延遲（分數取樣）、不同增益、獨立的背景噪音。
- 三支手機各自在不同時間開始錄音：B 晚 130 ms、C 早 310 ms（以 A 為準）。
- C 的取樣時脈比 A 快 25 ppm（偏移隨時間線性增加）。
- 主控手機（靠近 A）在第 4 秒與倒數第 2 秒各播一次同步嗶聲。
"""
import json
import os
import sys
import tempfile

import numpy as np
import scipy.signal as ss
import soundfile as sf

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from sync_chirp import chirp_template, detect_chirps, CHIRP_F0_HZ, CHIRP_F1_HZ, CHIRP_DURATION_S  # noqa: E402
import analyze_multi_mic as amm  # noqa: E402

SR = 48000
DUR = 20.0
RNG = np.random.default_rng(20261110)
START = {"A": 0.0, "B": 0.130, "C": -0.310}         # 錄音開始時間（相對 A，秒）
MACHINE_DELAY = {"A": 0.0021, "B": 0.00437, "C": 0.00305}   # 機台到各麥克風（秒）
CHIRP_DELAY = {"A": 0.0003, "B": 0.0049, "C": 0.0071}      # 主控手機到各麥克風（秒）
GAIN = {"A": 1.0, "B": 0.7, "C": 1.3}
CLOCK_PPM = {"A": 0.0, "B": 0.0, "C": 25.0}           # C 的取樣時脈快 25 ppm（不同手機的石英誤差）
CHIRP_TIMES = [4.0, DUR - 2.0]                       # 嗶聲在「世界時間」的播放時刻


def _shift(x, sec):
    return amm.frac_shift(x, -sec * SR)              # 延遲 sec 秒


def world_signals():
    n = int((DUR + 1.0) * SR)
    t = np.arange(n) / SR
    on = (t >= 3.0).astype(float)
    machine = np.zeros(n)
    for k in range(1, 13):
        jitter = np.cumsum(RNG.normal(0, 0.002, n))
        machine += (1.0 / k) * np.sin(2 * np.pi * 160 * k * t + jitter)
    import scipy.signal as ss
    sos = ss.butter(4, [1000, 6000], btype="band", fs=SR, output="sos")
    machine = 0.05 * on * (machine + 3.0 * ss.sosfilt(sos, RNG.normal(0, 1, n)))
    chirp = np.zeros(n)
    tpl = chirp_template(SR)
    for tc in CHIRP_TIMES:
        i = int(tc * SR)
        chirp[i:i + len(tpl)] += 0.08 * tpl
    return machine, chirp


def recordings(with_chirp=True):
    machine, chirp = world_signals()
    rec = {}
    for k in ("A", "B", "C"):
        y = GAIN[k] * _shift(machine, MACHINE_DELAY[k])
        if with_chirp:
            y = y + _shift(chirp, CHIRP_DELAY[k])
        y = y + 0.004 * RNG.normal(0, 1, len(y))     # 各手機獨立背景噪音
        eps = CLOCK_PPM[k] * 1e-6
        if eps:
            y = ss.resample(y, int(round(len(y) * (1 + eps))))
        i0 = int(round((START[k] + 0.5) * SR * (1 + eps)))   # 世界時間 0.5 s 為 A 的開始
        rec[k] = y[i0:i0 + int(DUR * SR) - int(0.4 * SR)]
    return rec


def expected_offset(k):
    """x[n + D] 對應 A[n] 的 D（取樣點），以機台聲為準；有時脈漂移時為 t = 0 的值。"""
    return ((MACHINE_DELAY[k] - MACHINE_DELAY["A"]) - (START[k] - START["A"])) * SR


def test_chirp_template_contract():
    tpl = chirp_template(SR)
    assert len(tpl) == int(round(SR * CHIRP_DURATION_S))
    assert abs(np.max(np.abs(tpl)) - 0.8) < 0.01
    # 瞬時頻率：前 1/10 與後 1/10 的過零率對應 F0、F1 附近
    def zc_freq(seg):
        return np.sum(np.abs(np.diff(np.sign(seg))) > 0) / 2 / (len(seg) / SR)
    m = len(tpl) // 10
    assert abs(zc_freq(tpl[m:2 * m]) - (CHIRP_F0_HZ + 0.15 * (CHIRP_F1_HZ - CHIRP_F0_HZ))) < 150
    assert abs(zc_freq(tpl[-2 * m:-m]) - (CHIRP_F0_HZ + 0.85 * (CHIRP_F1_HZ - CHIRP_F0_HZ))) < 150


def test_detects_chirps_in_machine_noise():
    rec = recordings(with_chirp=True)
    for k in ("A", "B", "C"):
        found = detect_chirps(rec[k], SR)
        assert len(found) == 2, (k, found)
        for (ts, _), tc in zip(found, CHIRP_TIMES):
            truth = tc + CHIRP_DELAY[k] - (START[k] + 0.5)
            assert abs(ts - truth) < 0.001, (k, ts, truth)


def test_no_false_chirp_without_beep():
    rec = recordings(with_chirp=False)
    for k in ("A", "B", "C"):
        assert detect_chirps(rec[k], SR) == [], k


def test_end_to_end_three_mics():
    rec = recordings(with_chirp=True)
    with tempfile.TemporaryDirectory() as d:
        paths = {}
        for k, y in rec.items():
            paths[k] = os.path.join(d, f"{k}.wav")
            sf.write(paths[k], y.astype(np.float32), SR, subtype="FLOAT")
        J = amm.run(paths, os.path.join(d, "out"), "synthetic")
        for k in ("B", "C"):
            s = J["sync"][f"{k}_vs_A"]
            assert s["coarse"]["method"] == "chirp", s["coarse"]
            assert abs(s["drift_ppm"] - CLOCK_PPM[k]) < 1.0, (k, s["drift_ppm"])
            assert abs(s["coarse"]["drift_ppm_from_chirps"] - CLOCK_PPM[k]) < 5, (k, s["coarse"])
            aa = s["after_alignment"]
            assert abs(aa["fine_offset_samples"]) < 0.25 and abs(aa["drift_ppm"]) < 0.5, (k, aa)
            lo, hi = aa["offset_spread_p5_p95_samples"]
            assert hi - lo < 0.5, (k, aa)
        s = J["sync"]["B_vs_A"]
        assert s["drift_compensated"] is False
        assert abs(s["fine_offset_samples"] - expected_offset("B")) < 0.25, (s["fine_offset_samples"], expected_offset("B"))
        assert J["sync"]["C_vs_A"]["drift_compensated"] is True
        assert set(J["phase"]) == {"A-B", "A-C", "B-C"}
        for pair, P in J["phase"].items():
            assert P["frac_bins_coh_ge_0p5"] > 0.30, (pair, P["frac_bins_coh_ge_0p5"])
            med = P["residual_tdoa_windows"]["median_samples"]
            assert med is not None and abs(med) < 0.5, (pair, med)
        br = J["background_removal"]
        # 停機的前 3 秒只有各手機獨立噪音：相干度增益應壓得比機台運轉時多
        assert br["attenuation_db_quiet_frames_bottom20pct"] < br["attenuation_db_loud_frames_top20pct"] - 3, br
        out = os.path.join(d, "out")
        for name in ["fig1_sync.png", "fig2_phase_AB.png", "fig2_phase_AC.png", "fig2_phase_BC.png",
                     "fig3_background_removal.png", "fig4_removal_spectra.png", "summary.json",
                     "A_aligned.wav", "B_aligned.wav", "C_aligned.wav", "final_coherence_plus_floor.wav"]:
            assert os.path.getsize(os.path.join(out, name)) > 0, name
        return J


def test_two_mic_envelope_fallback():
    rec = recordings(with_chirp=False)
    with tempfile.TemporaryDirectory() as d:
        paths = {}
        for k in ("A", "B"):
            paths[k] = os.path.join(d, f"{k}.wav")
            sf.write(paths[k], rec[k].astype(np.float32), SR, subtype="FLOAT")
        J = amm.run(paths, os.path.join(d, "out"))
        s = J["sync"]["B_vs_A"]
        assert s["coarse"]["method"] == "envelope"
        assert abs(s["fine_offset_samples"] - expected_offset("B")) < 0.25, s["fine_offset_samples"]


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in tests:
        try:
            r = fn()
            print(f"PASS {fn.__name__}")
            if fn.__name__ == "test_end_to_end_three_mics" and r:
                print("     ", json.dumps({k: [round(v["fine_offset_samples"], 3), round(v["drift_ppm"], 2),
                                            round(v["after_alignment"]["fine_offset_samples"], 3)]
                                        for k, v in r["sync"].items()}),
                      "expected t0", {k: round(expected_offset(k), 3) for k in ("B", "C")},
                      "coh>=0.5", {p: round(v["frac_bins_coh_ge_0p5"], 2) for p, v in r["phase"].items()},
                      "att quiet/loud", round(r["background_removal"]["attenuation_db_quiet_frames_bottom20pct"], 1),
                      round(r["background_removal"]["attenuation_db_loud_frames_top20pct"], 1))
        except AssertionError as e:
            failed += 1
            print(f"FAIL {fn.__name__}: {e}")
    print(f"{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
