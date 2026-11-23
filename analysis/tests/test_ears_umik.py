"""雙聲道同一時鐘裝置（例如 miniDSP EARS）＋獨立時鐘麥克風（例如 UMIK-2）的測試。

執行（不需要 pytest，也不需要接上裝置）：
  python -X utf8 analysis/tests/test_ears_umik.py

合成情境
- A＝EARS 左、B＝EARS 右：同一時鐘、同時開始；機台聲到 B 比到 A 晚 0.25 ms（48 kHz 時 12 取樣點）。
- C＝UMIK-2：自己的時鐘（快 25 ppm）、早 310 ms 開始錄。
"""
import json
import os
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

import numpy as np
import soundfile as sf

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import offline  # noqa: E402
import record_usb  # noqa: E402
import test_synthetic as ts  # noqa: E402
import worker  # noqa: E402

TDOA_S = 0.00025
TDOA_SAMPLES = TDOA_S * ts.SR


def ns(**kw):
    base = {"a": None, "b": None, "c": None, "stereo_ab": None, "ab_spacing_m": None, "temperature_c": 20.0, "note": ""}
    return type("Args", (), {**base, **kw})


@contextmanager
def ears_scene():
    """把 test_synthetic 的三手機情境改成：A、B 同時鐘同起點，B 的機台聲晚 TDOA_S。"""
    saved = {n: dict(getattr(ts, n)) for n in ("START", "MACHINE_DELAY", "CHIRP_DELAY", "CLOCK_PPM")}
    try:
        ts.START["B"] = ts.START["A"]
        ts.CLOCK_PPM["B"] = ts.CLOCK_PPM["A"]
        ts.MACHINE_DELAY["B"] = ts.MACHINE_DELAY["A"] + TDOA_S
        ts.CHIRP_DELAY["B"] = ts.CHIRP_DELAY["A"] + 0.0002
        yield ts.recordings(with_chirp=True)
    finally:
        for n, v in saved.items():
            getattr(ts, n).clear()
            getattr(ts, n).update(v)


def write_inputs(rec, d):
    n = min(len(rec["A"]), len(rec["B"]))
    stereo = Path(d) / "ears.wav"
    sf.write(stereo, np.stack([rec["A"][:n], rec["B"][:n]], axis=1).astype(np.float32), ts.SR, subtype="PCM_24")
    mono = Path(d) / "umik2.wav"
    sf.write(mono, rec["C"].astype(np.float32), ts.SR, subtype="PCM_24")
    return stereo, mono


_CACHE = {}


def full_run():
    """EARS＋UMIK-2、間距 0.15 m 的完整分析；多個測試共用一次結果。"""
    if "R" not in _CACHE:
        with ears_scene() as rec, tempfile.TemporaryDirectory() as d:
            stereo, mono = write_inputs(rec, d)
            out = Path(d) / "out"
            R = offline.cmd_run(ns(stereo_ab=str(stereo), c=str(mono), ab_spacing_m=0.15, out=str(out)))
            J = json.loads((out / "summary.json").read_text(encoding="utf-8"))
            raw_b, _ = sf.read(out / "input" / "B.wav", dtype="float32")
            kept_b, _ = sf.read(out / "B_aligned.wav", dtype="float32")
            assert (out / "fig1_sync.png").exists() and (out / "fig2_phase_AB.png").exists()
            assert not (out / "input" / "_stereo_tmp.wav").exists()
            _CACHE.update(R=R, J=J, raw_b=raw_b, kept_b=kept_b)
    return _CACHE


def test_same_clock_pair_keeps_acoustic_delay_and_separate_mic_is_aligned():
    c = full_run()
    R, J = c["R"], c["J"]
    assert R["alignment"]["verified"] is True, R["alignment"]
    assert R["alignment"]["channels"] == ["A", "B", "C"]
    assert R["alignment"]["same_clock_pairs"] == ["B_vs_A"]
    assert R["sources"] == {"A": "ears.wav（左聲道）", "B": "ears.wav（右聲道）", "C": "umik2.wav"}
    b = J["sync"]["B_vs_A"]
    assert b["same_clock"] is True and b["aligned"] is False and "after_alignment" not in b
    assert abs(b["acoustic_tdoa_samples"] - TDOA_SAMPLES) < 0.3, b       # B 晚到 12 取樣點，量得到、沒有被抹掉
    assert abs(b["tdoa_trend_ppm"]) < 1.0 and "clock_warning" not in b, b
    cc = J["sync"]["C_vs_A"]
    assert "same_clock" not in cc and cc["drift_compensated"] is True
    assert abs(cc["drift_ppm"] - 25.0) < 1.5, cc
    assert abs(cc["after_alignment"]["fine_offset_samples"]) < 0.3, cc


def test_same_clock_track_is_written_unshifted():
    c = full_run()
    n = len(c["kept_b"])
    assert n > 10 * ts.SR
    assert np.array_equal(c["kept_b"], c["raw_b"][:n])


def test_phase_slope_of_same_clock_pair_equals_acoustic_delay():
    P = full_run()["J"]["phase"]["A-B"]
    tau_us = P["residual_delay_from_phase_slope_us"]
    assert abs(abs(tau_us) - 1e6 * TDOA_S) < 30, tau_us                 # 相位斜率 ≈ 250 µs，不是 0
    med = P["residual_tdoa_windows"]["median_samples"]
    assert med is not None and abs(abs(med) - TDOA_SAMPLES) < 0.5, med


def test_spacing_gives_physical_limit_and_aliasing_frequency():
    sp = full_run()["J"]["sync"]["B_vs_A"]["spacing"]
    c = 331.3 + 0.606 * 20.0
    assert abs(sp["max_tdoa_samples"] - 0.15 / c * ts.SR) < 1e-6
    assert abs(sp["aliasing_hz"] - c / 0.30) < 1e-6
    assert sp["tdoa_over_straight_line_limit"] is False and sp["tdoa_physically_possible"] is True
    steer = full_run()["J"]["background_removal"]["settings"]["steered_same_clock_samples"]
    assert abs(steer["B"] - TDOA_SAMPLES) < 0.3, steer


def test_stereo_only_and_impossible_spacing_fails_verdict():
    """只有 EARS（沒有第三支）也能分析；間距填 2 cm 時，12 取樣點的時間差物理上不可能 → 判定不通過。"""
    with ears_scene() as rec, tempfile.TemporaryDirectory() as d:
        stereo, _ = write_inputs(rec, d)
        R = offline.cmd_run(ns(stereo_ab=str(stereo), ab_spacing_m=0.02, out=str(Path(d) / "out")))
    v = R["alignment"]
    assert v["channels"] == ["A", "B"]
    assert v["verified"] is False and "B_vs_A" in v["failed_pairs"], v
    assert "間距" in v["failed_pairs"]["B_vs_A"]
    assert R["pairs"]["B_vs_A"]["tdoa_over_straight_line_limit"] is True


def test_stereo_input_validation():
    with tempfile.TemporaryDirectory() as d:
        y = 0.1 * np.random.default_rng(3).normal(0, 1, ts.SR).astype(np.float32)
        mono = Path(d) / "mono.wav"
        sf.write(mono, y, ts.SR)
        dual = Path(d) / "dual_mono.wav"
        sf.write(dual, np.stack([y, y], axis=1), ts.SR)
        cases = [
            (ns(stereo_ab=str(mono), out=str(Path(d) / "o1")), "不是雙聲道"),
            (ns(stereo_ab=str(dual), out=str(Path(d) / "o2")), "完全相同"),
            (ns(stereo_ab=str(dual), a=str(mono), out=str(Path(d) / "o3")), "不要再給"),
            (ns(a=str(mono), b=str(mono), ab_spacing_m=0.1, out=str(Path(d) / "o4")), "只用在"),
            (ns(a=str(mono), out=str(Path(d) / "o5")), "請給 --a 與 --b"),
            (ns(stereo_ab=str(dual), ab_spacing_m=-1.0, out=str(Path(d) / "o6")), "正數"),
        ]
        for args, needle in cases:
            try:
                offline.cmd_run(args)
            except SystemExit as e:
                assert needle in str(e), (needle, str(e))
            else:
                raise AssertionError(f"應該拒絕：{needle}")


def test_verdict_same_clock_rules():
    ok = {"channels": ["A", "B"], "sync": {"B_vs_A": {"same_clock": True, "acoustic_tdoa_samples": 12.0}}}
    v = worker.alignment_verdict(ok)
    assert v["verified"] is True and v["same_clock_pairs"] == ["B_vs_A"], v
    bad = {"channels": ["A", "B"], "sync": {"B_vs_A": {"same_clock": True, "acoustic_tdoa_samples": 60.0, "spacing": {
        "spacing_m": 0.15, "max_tdoa_samples": 21.0, "tdoa_physically_possible": False}}}}
    v = worker.alignment_verdict(bad)
    assert v["verified"] is False and "1.5 倍" in v["failed_pairs"]["B_vs_A"], v
    # 欄位殘缺也不能丟例外
    v = worker.alignment_verdict({"channels": ["A", "B"], "sync": {"B_vs_A": {
        "same_clock": True, "spacing": {"tdoa_physically_possible": False}}}})
    assert v["verified"] is False, v
    # 只有明確的 True 才算同一時鐘；其他值照一般規則，缺 after_alignment 就不通過
    v = worker.alignment_verdict({"channels": ["A", "B"], "sync": {"B_vs_A": {"same_clock": "yes"}}})
    assert v["verified"] is False and "same_clock_pairs" not in v, v
    # 手機路徑的輸出格式不變
    phone = worker.alignment_verdict({"channels": ["A", "B"], "sync": {"B_vs_A": {
        "after_alignment": {"fine_offset_samples": 0.1, "drift_ppm": 0.2}}}})
    assert set(phone) == {"verified", "channels", "failed_pairs", "criteria"} and phone["verified"] is True


def test_recorder_device_parsing_and_selection():
    text = '''[dshow @ 000001] Could not enumerate video devices (or none found).
[dshow @ 000001] "麥克風排列 (Realtek(R) Audio)" (audio)
[dshow @ 000001]   Alternative name "@device_cm_{33D9A762}\\wave_{E8DB0F06}"
[dshow @ 000001] "Line (2- E.A.R.S Gain: 18dB)" (audio)
[dshow @ 000001]   Alternative name "@device_cm_{33D9A762}\\wave_{AAAA}"
[dshow @ 000001] "Microphone (Umik-2)" (audio)
[dshow @ 000001] "USB Camera" (video)
Error opening input file dummy.'''
    devs = record_usb.parse_devices(text)
    assert devs == ["麥克風排列 (Realtek(R) Audio)", "Line (2- E.A.R.S Gain: 18dB)", "Microphone (Umik-2)"], devs
    assert record_usb.pick(devs, "e.a.r.s", "雙聲道") == "Line (2- E.A.R.S Gain: 18dB)"
    assert record_usb.pick(devs, "UMIK", "單聲道") == "Microphone (Umik-2)"
    for needle, why in (("nothing", "找不到"), ("(", "有 3 台符合")):
        try:
            record_usb.pick(devs, needle, "雙聲道")
        except SystemExit as e:
            assert why in str(e) and "Umik-2" in str(e), str(e)
        else:
            raise AssertionError("應該拒絕")
    # 2026-11-16 實機：EARS 的名稱是「麥克風 (E.A.R.S Gain: 24dB)」，冒號讓 ffmpeg 回報 Malformed dshow input string。
    # 所以一律改用名稱下一行的裝置識別碼開啟；識別碼沒有冒號。
    ids = record_usb.parse_device_ids(text)
    assert ids == {"麥克風排列 (Realtek(R) Audio)": "@device_cm_{33D9A762}\\wave_{E8DB0F06}",
                   "Line (2- E.A.R.S Gain: 18dB)": "@device_cm_{33D9A762}\\wave_{AAAA}"}, ids
    spec = record_usb.input_spec("Line (2- E.A.R.S Gain: 18dB)", ids)
    assert spec == "@device_cm_{33D9A762}\\wave_{AAAA}" and ":" not in spec
    assert record_usb.input_spec("Microphone (Umik-2)", ids) == "Microphone (Umik-2)"      # 沒有識別碼、名稱沒冒號：用名稱
    try:
        record_usb.input_spec("X (Gain: 6dB)", {})
    except SystemExit as e:
        assert "冒號" in str(e), e
    else:
        raise AssertionError("名稱含冒號又沒有識別碼時應該明確報錯")


def test_unmeasurable_same_clock_delay_is_reported_plainly():
    """2026-11-16 實機：只有室內環境音時量不到到達時間差，報告要明講，不能印出 None 取樣點。"""
    import contextlib
    import io
    R = {"alignment": {"verified": True, "channels": ["A", "B"], "failed_pairs": {}, "same_clock_pairs": ["B_vs_A"],
                       "criteria": {"max_residual_samples": 2.0, "max_residual_ppm": 5.0}},
         "durations_s": {"A": 10.0, "B": 10.0}, "chirps_detected_s": {"A": [], "B": []}, "codec_cutoff_hz": {},
         "pairs": {"B_vs_A": {"same_clock": True, "aligned": False, "acoustic_tdoa_samples": None,
                              "acoustic_tdoa_us": None, "tdoa_spread_p5_p95_samples": [], "tdoa_trend_ppm": None,
                              "clear_windows": "None/None", "spacing_m": None, "max_tdoa_samples": None,
                              "aliasing_hz": None, "tdoa_over_straight_line_limit": None, "warning": "精對齊失敗"}},
         "level_difference": {}, "phase": {}}
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        offline.print_report(R)
    text = buf.getvalue()
    assert "量不到" in text and "None 取樣點" not in text, text
    assert "同一時鐘，硬體同步，不需要對齊" in text and "殘餘偏移" not in text, text


def test_recorder_command_opens_both_devices_in_one_process():
    cmd = record_usb.build_cmd("ffmpeg", [("EARS dev", 2, Path("s.wav")), ("UMIK dev", 1, Path("m.wav"))], 60, 24)
    assert cmd.count("-f") == 2 and cmd.count("dshow") == 2
    assert "audio=EARS dev" in cmd and "audio=UMIK dev" in cmd
    i0, i1 = cmd.index("audio=EARS dev"), cmd.index("audio=UMIK dev")
    assert cmd[i0 - 9:i0 - 1] == ["-sample_rate", "48000", "-channels", "2", "-sample_size", "24",
                                  "-audio_buffer_size", "50"], cmd[i0 - 9:i0]
    assert cmd[i1 - 7:i1 - 5] == ["-channels", "1"]
    m0, m1 = cmd.index("0:a"), cmd.index("1:a")
    assert cmd[m0 + 1:m0 + 3] == ["-t", "60"] and cmd[m1 - 1] == "-map" and cmd[-1] == "m.wav"
    assert cmd.count("pcm_s24le") == 2
    assert record_usb.build_cmd("ffmpeg", [("x", 2, Path("s.wav"))], 1.5, 16).count("pcm_s16le") == 1


def test_recorder_file_checks():
    rng = np.random.default_rng(5)
    with tempfile.TemporaryDirectory() as d:
        def w(name, y):
            sf.write(Path(d) / name, y.astype(np.float32), ts.SR, subtype="PCM_16")
            return Path(d) / name
        left, right = 0.1 * rng.normal(0, 1, 2 * ts.SR), 0.1 * rng.normal(0, 1, 2 * ts.SR)
        st, pr = record_usb.check_file(w("good.wav", np.stack([left, right], 1)), 2, 2.0)
        assert pr == [] and st["channels"] == 2 and st["duration_s"] == 2.0, (st, pr)
        _, pr = record_usb.check_file(w("dual.wav", np.stack([left, left], 1)), 2, 2.0)
        assert any("完全相同" in x for x in pr), pr
        _, pr = record_usb.check_file(w("clip.wav", np.stack([np.clip(20 * left, -1, 1), right], 1)), 2, 2.0)
        assert any("第 1 聲道破音" in x for x in pr) and not any("第 2 聲道破音" in x for x in pr), pr
        _, pr = record_usb.check_file(w("silent.wav", np.stack([left, np.zeros_like(left)], 1)), 2, 2.0)
        assert any("第 2 聲道幾乎沒有聲音" in x for x in pr), pr
        _, pr = record_usb.check_file(w("short.wav", np.stack([left, right], 1)), 2, 10.0)
        assert any("只錄到" in x for x in pr), pr
        _, pr = record_usb.check_file(w("mono.wav", left), 2, 2.0)
        assert any("聲道數是 1" in x for x in pr), pr


def test_windows_effects_detection():
    """2026-11-16 實機：Windows 替 EARS 掛了語音清晰度（VocaEffectPack），左右相同的穩定噪音播了 1 秒就被壓成無聲。"""
    pack = "{9e6136e0-57ab-4949-b57a-3627be142855},100"
    ears_fx = {pack: "SWD\\DRIVERENUM\\{96bedf2c-18cb-4a15-b821-5e95ed0fea61}#VocaEffectPack&1&226863a3&0"}
    assert record_usb.effects_status(ears_fx, {}) == (True, ["VocaEffectPack"])
    # 使用者把「音訊增強」關掉之後：效果包還登記著，但不再作用
    assert record_usb.effects_status({**ears_fx, record_usb._FX_DISABLE: 1}, {})[0] is False
    assert record_usb.effects_status(ears_fx, {record_usb._FX_DISABLE: 1})[0] is False
    assert record_usb.effects_status({**ears_fx, record_usb._FX_DISABLE: 0}, {})[0] is True
    # 沒有登記任何效果
    assert record_usb.effects_status({}, {}) == (False, [])
    # 只有識別碼、沒有看得懂的名稱：回報數量；名稱最多列 4 個、不重複
    active, effects = record_usb.effects_status({"{a},1": "{4BD94DA9}", "{a},2": 0, "{a},3": b"xx"}, {})
    assert active is True and effects == ["3 項效果設定"], effects
    many = {f"{{k}},{i}": f"Effect {i % 6}" for i in range(12)}
    assert record_usb.effects_status(many, {})[1] == ["Effect 0", "Effect 1", "Effect 2", "Effect 3"]


def test_recorder_refuses_repository_output():
    try:
        record_usb.cmd_record(type("A", (), {"out": str(offline.REPO / "analysis" / "rec_should_not_exist"),
                                             "stereo": "x", "mono": None, "seconds": 1.0, "bits": 24, "note": ""}))
    except SystemExit as e:
        assert "儲存庫" in str(e), e
    else:
        raise AssertionError("應該拒絕")
    assert not (offline.REPO / "analysis" / "rec_should_not_exist").exists()


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
