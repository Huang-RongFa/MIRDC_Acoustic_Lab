"""清晰度分數（GCC-PHAT 峰值 ÷ 背景中位數）不可以隨搜尋範圍改變。

執行（不需要 pytest）：
  python -X utf8 analysis/tests/test_score_scale.py

為什麼要有這個測試
- 2026-11-23 的真實錄音（一支雙聲道裝置＋一支獨立麥克風，房間反射多）：第一次量用 ±25 ms，
  51 窗裡有 28 窗清楚；對齊後複驗用 ±5 ms，同一份資料 0 窗清楚，結果被判成「對齊後無法重新量測」。
- 原因：背景中位數只取搜尋範圍內的延遲。主峰附近有反射時，範圍越窄、中位數越高、分數越低。
  門檻 20 是在 ±25 ms 下定的，拿到 ±5 ms 用就變嚴了。
- 修正後的定義：背景一律取 ±SCORE_REF_MS（25 ms）的延遲範圍；搜尋範圍只決定去哪裡找峰值。

合成情境：100–3000 Hz 的共同聲源，第二支麥克風除了直達聲還有 12 個反射（主峰前後 ±4 ms 內），
兩支各有獨立噪音，第二支的取樣時脈快 18 ppm。門檻與判定標準都沿用原本的數值，沒有為這個測試調整。
"""
import os
import sys
import tempfile

import numpy as np
import scipy.signal as ss
import soundfile as sf

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import analyze_multi_mic as amm  # noqa: E402

SR = 48000
DELAY = 37.3
PPM = 18.0
ECHOES = ((0.0, 1.0), (23.0, 0.8), (41.0, 0.75), (67.0, 0.7), (97.0, 0.7), (131.0, 0.65), (163.0, 0.6), (199.0, 0.6),
          (-29.0, 0.7), (-71.0, 0.65), (-113.0, 0.6), (-157.0, 0.6), (-203.0, 0.55))
_CACHE = {}


def reverberant_pair(seed=1, noise=0.05, dur=24.0):
    key = (seed, noise, dur)
    if key not in _CACHE:
        rng = np.random.default_rng(seed)
        n = int(dur * SR)
        s = ss.sosfilt(ss.butter(4, [100, 3000], btype="band", fs=SR, output="sos"), rng.normal(0, 1, n + SR))
        a = s[:n] + noise * rng.normal(0, 1, n)
        b = sum(g * amm.frac_shift(s, -(DELAY + d)) for d, g in ECHOES)
        b = ss.resample(b, int(round(len(b) * (1 + PPM * 1e-6))))[:n] + noise * rng.normal(0, 1, n)
        _CACHE[key] = (a, b)
    return _CACHE[key]


def _legacy_score(xs, ys, maxlag):
    """修正前的算法，原樣抄在這裡當對照：背景中位數取搜尋範圍內的延遲。"""
    xs = xs * np.hanning(len(xs))
    ys = ys * np.hanning(len(ys))
    n = 1 << int(np.ceil(np.log2(len(xs) + len(ys))))
    R = np.fft.rfft(xs, n) * np.conj(np.fft.rfft(ys, n))
    R = R / (np.abs(R) + 1e-15)
    c = np.fft.irfft(R, n)
    c = np.concatenate([c[-maxlag:], c[: maxlag + 1]])
    k = int(np.argmax(np.abs(c)))
    return float(np.abs(c[k]) / (np.median(np.abs(c)) + 1e-20))


def _windows(a, b, d0):
    """和 fine_offset 相同的帶通與切窗，回傳每一窗的兩段訊號。"""
    sos = ss.butter(4, [100, min(12000, 0.45 * SR)], btype="band", fs=SR, output="sos")
    xa, xb = ss.sosfiltfilt(sos, a), ss.sosfiltfilt(sos, b)
    m = 2 * SR
    out = []
    for t in np.arange(0.5, len(a) / SR - 2.5, 1.0):
        i = int(t * SR)
        if i + d0 < 0 or i + d0 + m > len(xb) or i + m > len(xa):
            continue
        out.append((xa[i:i + m], xb[i + d0:i + d0 + m]))
    return out


def test_first_pass_scores_are_bit_for_bit_unchanged():
    """第一次量（±25 ms）的分數不可以因為這次修正而改變：既有錄音的精對齊結果要維持原樣。"""
    a, b = reverberant_pair()
    _, info, fit = amm.fine_offset(a, b, SR, 37, search_ms=25)
    legacy = np.array([_legacy_score(xs, ys, int(0.025 * SR)) for xs, ys in _windows(a, b, 37)])
    assert len(legacy) == info["windows_total"], (len(legacy), info["windows_total"])
    assert np.array_equal(fit[0][:, 2], legacy), float(np.max(np.abs(fit[0][:, 2] - legacy)))
    assert info["windows_phat_ge_20"] >= 15, info["windows_phat_ge_20"]


def test_score_is_independent_of_search_range():
    """同一份資料、同一個峰值：搜尋 ±5、±10、±25 ms 得到的分數必須相同，清楚的窗數也必須相同。"""
    a, b = reverberant_pair()
    ref_d, ref_info, ref_fit = amm.fine_offset(a, b, SR, 37, search_ms=25)
    for ms in (5, 10):
        try:
            d, info, fit = amm.fine_offset(a, b, SR, 37, search_ms=ms)
        except RuntimeError as e:
            raise AssertionError(f"搜尋 ±{ms} ms 時量不到，但 ±25 ms 有 {ref_info['windows_phat_ge_20']} 窗清楚：{e}")
        same_peak = np.abs(fit[0][:, 1] - ref_fit[0][:, 1]) < 0.01
        assert same_peak.mean() >= 0.9, f"±{ms} ms 只有 {same_peak.mean():.0%} 的窗找到同一個峰"
        diff = np.max(np.abs(fit[0][same_peak, 2] / ref_fit[0][same_peak, 2] - 1))
        assert diff < 1e-9, f"±{ms} ms 的分數和 ±25 ms 差了 {diff:.3g}（相對）"
        assert info["windows_phat_ge_20"] == ref_info["windows_phat_ge_20"], (ms, info["windows_phat_ge_20"],
                                                                          ref_info["windows_phat_ge_20"])
        assert abs(d - ref_d) < 0.05, (ms, d, ref_d)


def test_function_level_score_ignores_maxlag_when_reference_is_fixed():
    """xcorr_peak：背景範圍固定（ref_lag）時，搜尋範圍 3、5、25、50 ms 的分數相同。1 秒窗也一樣（相位步驟用 1 秒窗、±3 ms）。"""
    a, b = reverberant_pair()
    sos = ss.butter(4, [100, 12000], btype="band", fs=SR, output="sos")
    ref = int(amm.SCORE_REF_MS / 1000 * SR)
    for length in (SR, 2 * SR):
        xs = ss.sosfiltfilt(sos, a[5 * SR:5 * SR + length])
        ys = ss.sosfiltfilt(sos, b[5 * SR + 48:5 * SR + 48 + length])
        base_lag, base = amm.xcorr_peak(xs, ys, ref, True, ref_lag=ref)
        assert abs(base_lag) < 0.003 * SR, base_lag            # 峰值落在最窄的搜尋範圍內，四種範圍才比得起來
        for ms in (3, 5, 50):
            lag, score = amm.xcorr_peak(xs, ys, int(ms / 1000 * SR), True, ref_lag=ref)
            assert abs(lag - base_lag) < 1e-9 and abs(score / base - 1) < 1e-12, (length, ms, lag, base_lag, score, base)


def test_independent_noise_is_never_clear_at_any_search_range():
    """修正不可以讓沒有共同聲音的兩軌變成「清楚」：獨立噪音在任何搜尋範圍的分數都遠低於門檻。"""
    rng = np.random.default_rng(7)
    a, b = rng.normal(0, 1, 24 * SR), rng.normal(0, 1, 24 * SR)
    ref = int(amm.SCORE_REF_MS / 1000 * SR)
    worst = 0.0
    for ms in (3, 5, 10, 25, 50):
        for xs, ys in _windows(a, b, 0):
            worst = max(worst, amm.xcorr_peak(xs, ys, int(ms / 1000 * SR), True, ref_lag=ref)[1])
        try:
            amm.fine_offset(a, b, SR, 0, search_ms=ms)
            raise AssertionError(f"獨立噪音在 ±{ms} ms 被當成可以對齊")
        except RuntimeError:
            pass
    assert worst < 0.6 * amm.PHAT_MIN, worst


def test_verification_after_alignment_uses_the_same_scale():
    """整條流程：第一次量得到的錄音，對齊後複驗也要量得到，殘差在原本的判定標準內。"""
    from worker import alignment_verdict
    a, b = reverberant_pair()
    with tempfile.TemporaryDirectory() as d:
        paths = {}
        for k, x in (("A", a), ("B", b)):
            paths[k] = os.path.join(d, f"{k}.wav")
            sf.write(paths[k], (0.05 * x).astype(np.float32), SR, subtype="FLOAT")
        J = amm.run(paths, os.path.join(d, "out"))
    s = J["sync"]["B_vs_A"]
    after = s["after_alignment"]
    assert s["windows_phat_ge_20"] >= 15, s["windows_phat_ge_20"]
    assert "error" not in after, after
    assert after["windows_phat_ge_20"] >= 0.8 * s["windows_phat_ge_20"], (after["windows_phat_ge_20"], s["windows_phat_ge_20"])
    assert abs(after["fine_offset_samples"]) <= 2.0, after["fine_offset_samples"]
    assert abs(after["drift_ppm"]) <= 5.0, after["drift_ppm"]
    assert abs(s["drift_ppm"] - PPM) < 5.0, s["drift_ppm"]
    verdict = alignment_verdict(J)
    assert verdict["verified"], verdict
    return J


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in tests:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {fn.__name__}: {e}")
        except Exception as e:  # noqa: BLE001  API 還不存在時也要算失敗，並把其他測試跑完
            failed += 1
            print(f"FAIL {fn.__name__}: {type(e).__name__}: {e}")
    print(f"{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
