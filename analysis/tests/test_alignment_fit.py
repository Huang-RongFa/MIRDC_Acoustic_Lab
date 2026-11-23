"""漂移的直線擬合不可以被「鎖到反射峰的窗」拉歪。

執行（不需要 pytest）：
  python -X utf8 analysis/tests/test_alignment_fit.py

為什麼要有這個測試
- 房間反射多時，少數幾個窗的 GCC-PHAT 峰值會落在反射上（離直達聲幾十個取樣點），分數仍然超過門檻。
- 原本用所有清楚的窗做最小平方直線。3/21 個窗偏了 23 個取樣點，直線就被拉高約 3.5 個取樣點；
  照這條線對齊之後，其餘 18 個窗都讀到 −3.4，超過「殘餘偏移 ≤ 2 取樣點」的標準。
- 修正後：先用對離群值不敏感的方法（Theil–Sen）找出直線，離這條線超過容許值的窗不參加最後的擬合。
  容許值 = max(2 取樣點, 3 × 1.4826 × MAD)。2 取樣點就是對齊判定本來的殘餘偏移標準，不是為這個測試挑的數字。
- 沒有離群窗時，結果必須和原本的最小平方直線完全相同。
"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import analyze_multi_mic as amm  # noqa: E402
import test_score_scale as scene  # noqa: E402
import test_synthetic as ts  # noqa: E402

SR = 48000


def test_line_without_outliers_is_exactly_least_squares():
    rng = np.random.default_rng(3)
    t = np.arange(1.5, 40.0, 1.0)
    o = 812.0 + 0.9 * t + rng.normal(0, 0.4, len(t))
    p, inlier = amm.robust_line(t, o)
    assert inlier.all(), int((~inlier).sum())
    assert np.array_equal(p, np.polyfit(t, o, 1)), (p, np.polyfit(t, o, 1))


def test_line_ignores_windows_locked_to_a_reflection():
    rng = np.random.default_rng(4)
    t = np.arange(1.5, 40.0, 1.0)
    o = 812.0 + 0.9 * t + rng.normal(0, 0.4, len(t))
    bad = np.zeros(len(t), bool)
    bad[[3, 9, 10, 17, 25, 31]] = True                       # 39 個窗裡 6 個（15%）鎖到 +23 取樣點的反射
    o[bad] += 23.0
    p, inlier = amm.robust_line(t, o)
    assert np.array_equal(inlier, ~bad), (np.where(~inlier)[0].tolist(), np.where(bad)[0].tolist())
    assert abs(p[0] - 0.9) < 0.02 and abs(p[1] - 812.0) < 0.5, p
    plain = np.polyfit(t, o, 1)
    assert abs(plain[1] - 812.0) > 2.0, plain                # 對照：一般最小平方會被拉歪超過 2 個取樣點


def test_line_keeps_a_noisy_but_single_cluster():
    """各窗本來就比較散（沒有第二個峰）時，不可以把正常的窗當離群值丟掉一大半。"""
    rng = np.random.default_rng(5)
    t = np.arange(1.5, 60.0, 1.0)
    o = 100.0 - 0.5 * t + rng.normal(0, 3.0, len(t))
    p, inlier = amm.robust_line(t, o)
    assert inlier.mean() >= 0.95, inlier.mean()
    assert abs(p[0] + 0.5) < 0.1, p


def test_line_with_two_points_still_works():
    p, inlier = amm.robust_line(np.array([1.5, 2.5]), np.array([10.0, 11.0]))
    assert inlier.all() and abs(p[0] - 1.0) < 1e-9 and abs(p[1] - 8.5) < 1e-9, p


def test_clean_recording_fit_is_unchanged():
    """沒有反射的合成錄音（25 ppm 漂移）：沒有窗被排除，直線和原本的最小平方完全相同。"""
    rec = ts.recordings(with_chirp=False)
    d0 = amm.coarse_envelope(rec["A"], rec["C"], SR)[0]
    _, info, (win, good, p, _) = amm.fine_offset(rec["A"], rec["C"], SR, d0)
    assert info["windows_rejected_as_outliers"] == 0, info["windows_rejected_as_outliers"]
    assert info["windows_used_for_fit"] == info["windows_phat_ge_20"], info
    assert np.array_equal(p, np.polyfit(win[good, 0], win[good, 1], 1)), p


def test_reverberant_recording_line_matches_the_direct_path():
    """反射多的合成錄音：直線要落在直達聲上。真值：t = 0 的偏移 37.3 取樣點、漂移 18 ppm。"""
    a, b = scene.reverberant_pair()
    d0 = amm.coarse_envelope(a, b, SR)[0]
    _, info, (win, good, p, _) = amm.fine_offset(a, b, SR, d0)
    assert info["windows_rejected_as_outliers"] >= 1, info
    assert info["windows_used_for_fit"] + info["windows_rejected_as_outliers"] == info["windows_phat_ge_20"], info
    assert abs(p[1] - scene.DELAY) < 1.0, p[1]
    assert abs(info["drift_ppm"] - scene.PPM) < 2.0, info["drift_ppm"]


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
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL {fn.__name__}: {type(e).__name__}: {e}")
    print(f"{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
