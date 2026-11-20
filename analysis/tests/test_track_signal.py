"""track_analysis.signal_contract / render 測試：合成訊號，答案由定義直接算出。

執行（不需要 pytest，也不連資料庫）：
  python -X utf8 analysis/tests/test_track_signal.py

期望值一律在本檔內依規格第 8 節的文字定義另外算一次（numpy.fft、手寫 Hann、手寫 Mel 與 DCT），
不拿被測函式的輸出互相比。
"""
import io
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from track_analysis import signal_contract as sc, render  # noqa: E402

import matplotlib.image as mpimg  # noqa: E402  （render 已把後端設成 Agg）

SR, N_FFT, HOP, N_BINS = 44100, 2048, 441, 1025
BIN_HZ = SR / N_FFT
RNG = np.random.default_rng(20261120)
PNG_SIGNATURE = bytes([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A])


def sine(freq, n, sr=SR, amp=1.0, phase=0.0):
    return amp * np.sin(2 * np.pi * freq * np.arange(n) / sr + phase)


def raises(exc, fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except exc as e:
        return e
    raise AssertionError(f"應該丟出 {exc.__name__}")


def ref_hann():
    return 0.5 - 0.5 * np.cos(2 * np.pi * np.arange(N_FFT) / N_FFT)      # periodic Hann 的定義式


def ref_stft(x):
    """逐窗用 numpy.fft 算的參考答案。"""
    w = ref_hann()
    count = 1 + (len(x) - N_FFT) // HOP
    out = np.empty((N_BINS, count))
    for k in range(count):
        spec = np.abs(np.fft.rfft(x[k * HOP:k * HOP + N_FFT] * w)) / w.sum()
        spec[1:-1] *= 2
        out[:, k] = spec
    return out


def ref_mel_points():
    top = 2595 * np.log10(1 + 22050 / 700)
    return np.array([700 * (10 ** (m * top / 65 / 2595) - 1) for m in range(66)])


def ref_mel_bank():
    pts, freqs = ref_mel_points(), np.arange(N_BINS) * BIN_HZ
    return np.stack([np.interp(freqs, pts[m:m + 3], [0.0, 1.0, 0.0], left=0.0, right=0.0) for m in range(64)])


def ref_dct2_ortho(rows):
    n = np.arange(rows)
    basis = np.cos(np.pi * (2 * n[None, :] + 1) * n[:, None] / (2 * rows)) * np.sqrt(2 / rows)
    basis[0] /= np.sqrt(2)
    return basis


def test_1_amplitude_scale_is_dbfs():
    n = SR
    f = 100 * BIN_HZ                                        # 正好落在第 100 個頻點
    amp, _ = sc.stft_amplitude(sine(f, n))
    db = sc.spectrogram_db(amp)
    assert (db.argmax(axis=0) == 100).all()
    assert np.abs(db[100] - 0.0).max() < 0.05, db[100]
    db01 = sc.spectrogram_db(sc.stft_amplitude(sine(f, n, amp=0.1))[0])
    assert (db01.argmax(axis=0) == 100).all() and np.abs(db01[100] + 20.0).max() < 0.05, db01[100]
    # DC 不乘二：0.5 的直流偏移 = 20*log10(0.5) = -6.02 dB（乘二的話會是 0 dB）
    dc = sc.spectrogram_db(sc.stft_amplitude(np.full(n, 0.5))[0])
    assert np.abs(dc[0] - 20 * np.log10(0.5)).max() < 1e-6, dc[0]
    # Nyquist 也不乘二：±1 交替 = 振幅 1 的 22050 Hz
    ny = sc.spectrogram_db(sc.stft_amplitude(np.cos(np.pi * np.arange(n)))[0])
    assert np.abs(ny[1024]).max() < 1e-6, ny[1024]
    # 任意訊號：與逐窗 numpy.fft 的參考答案一致
    x = 0.3 * RNG.normal(size=3 * SR // 2) + sine(1234.5, 3 * SR // 2, amp=0.4)
    got, _ = sc.stft_amplitude(x)
    assert got.dtype == np.float64 and got.shape == (N_BINS, 1 + (len(x) - N_FFT) // HOP)
    assert np.allclose(got, ref_stft(x), rtol=1e-9, atol=1e-12)
    assert np.array_equal(sc.spectrogram_db(got), 20 * np.log10(np.maximum(got, 1e-6)))


def test_2_frames_times_and_no_padding():
    for n, expect in [(2048, 1), (2048 + 440, 1), (2048 + 441, 2), (44100, 96), (2048 + 441 * 10 + 150, 11)]:
        amp, times = sc.stft_amplitude(RNG.normal(size=n))
        assert expect == 1 + (n - 2048) // 441
        assert amp.shape == (N_BINS, expect) and times.shape == (expect,), (n, amp.shape)
        assert times.dtype == np.float64
        assert all(times[k] == k * 441 / 44100 for k in range(expect)), n
    for n in (0, 1, 2047):
        raises(sc.NoData, sc.stft_amplitude, np.zeros(n))
    assert not issubclass(sc.NoData, ValueError)
    raises(ValueError, sc.stft_amplitude, np.zeros((2, 4096)))
    # 尾端湊不滿一窗的 150 個樣本裡放訊號：不能被補零後算進去
    n = 2048 + 441 * 10 + 150
    x = np.zeros(n)
    x[-100:] = 1.0
    amp, times = sc.stft_amplitude(x)
    assert amp.shape[1] == 11 and not amp.any(), amp.max()
    assert (sc.spectrogram_db(amp) == -120.0).all()
    # 同一段訊號去掉尾端零頭，結果完全相同
    y = RNG.normal(size=n)
    assert np.array_equal(sc.stft_amplitude(y)[0], sc.stft_amplitude(y[:2048 + 441 * 10])[0])


def test_3_digital_silence():
    amp, _ = sc.stft_amplitude(np.zeros(SR))
    db = sc.spectrogram_db(amp)
    assert db.shape == (N_BINS, 96) and (db == -120.0).all()
    mfcc = sc.mfcc_from_amplitude(amp)
    assert mfcc.shape == (20, 96) and np.isfinite(mfcc).all()
    # 64 個 Mel 頻帶都是 -120 dB：C0 = -120*sqrt(64) = -960，其餘為 0
    assert np.allclose(mfcc[0], -960.0, atol=1e-9) and np.abs(mfcc[1:]).max() < 1e-9, mfcc[:, 0]
    out = sc.analyze_channel(np.zeros(SR), SR)
    assert (out["spectrogram_db"] == -120.0).all() and np.isfinite(out["mfcc"]).all()


def test_4_mel_filterbank():
    bank = sc.mel_filterbank()
    assert bank.shape == (64, 1025) and bank.dtype == np.float64
    assert (bank >= 0).all() and bank.max() <= 1.0 + 1e-12
    pts, freqs = ref_mel_points(), np.arange(N_BINS) * BIN_HZ
    # 另外用 np.interp 寫的三角形，逐點一致
    assert np.allclose(bank, ref_mel_bank(), rtol=0, atol=1e-12)
    # 頂點高度 1、不做面積正規化：相鄰三角形在兩個中心之間相加必為 1
    inside = (freqs >= pts[1]) & (freqs <= pts[64])
    assert inside.sum() > 900 and np.abs(bank.sum(axis=0)[inside] - 1.0).max() < 1e-9
    # 由取樣點反推每個三角形的頂點：兩側各取兩點成直線，交點就是 (中心頻率, 峰值)
    apexes = {}
    for m in range(64):
        nz = np.flatnonzero(bank[m] > 0)
        up, down = nz[freqs[nz] <= pts[m + 1]], nz[freqs[nz] > pts[m + 1]]
        if len(up) < 2 or len(down) < 2:
            continue
        a1 = (bank[m, up[-1]] - bank[m, up[0]]) / (freqs[up[-1]] - freqs[up[0]])
        a2 = (bank[m, down[-1]] - bank[m, down[0]]) / (freqs[down[-1]] - freqs[down[0]])
        b1, b2 = bank[m, up[0]] - a1 * freqs[up[0]], bank[m, down[0]] - a2 * freqs[down[0]]
        centre = (b2 - b1) / (a1 - a2)
        apexes[m] = (centre, a1 * centre + b1)
    assert len(apexes) >= 60, len(apexes)
    for m, (centre, peak) in apexes.items():
        assert abs(peak - 1.0) < 1e-9, (m, peak)                      # 每個濾波器的峰值都是 1.0
        assert abs(centre - pts[m + 1]) < 1e-6, (m, centre, pts[m + 1])
    centres = [apexes[m][0] for m in sorted(apexes)]
    assert all(b > a for a, b in zip(centres, centres[1:]))
    assert (np.diff(bank.argmax(axis=1)) > 0).all()
    # 三個中心對 HTK 公式：mel = 2595*log10(1+f/700)，0..22050 Hz 之間 66 個等距 mel 點
    assert abs(pts[1] - 38.5123868963688) < 1e-9                       # 公式本身的數值錨點
    assert abs(BIN_HZ / bank[0, 1] - pts[1]) < 1e-9                    # 第 1 個：上升邊從 0 Hz 到中心
    assert abs(apexes[31][0] - 3185.1684067120527) < 1e-6              # 第 32 個
    assert abs(apexes[62][0] - pts[63]) < 1e-6                         # 第 63 個
    mel = 2595 * np.log10(1 + pts / 700)
    assert np.allclose(np.diff(mel), mel[-1] / 65, rtol=0, atol=1e-9)  # 等距
    # 第一個從 0 Hz 開始、最後一個在 22050 Hz 結束
    assert bank[0, 0] == 0.0 and bank[0, 1] > 0
    assert bank[-1, 1024] == 0.0 and bank[-1, 1023] > 0
    assert abs(bank[-1, 1023] - (22050 - freqs[1023]) / (22050 - pts[64])) < 1e-12
    assert not bank[:, 0].any() and not bank[:, 1024].any()
    bank[:] = 7.0                                                       # 回傳的是副本，改它不影響下一次
    assert sc.mel_filterbank().max() <= 1.0


def test_5_mfcc_matches_definition():
    n = 2 * SR
    x = 0.2 * RNG.normal(size=n) + sine(440, n, amp=0.5) + sine(5000, n, amp=0.1)
    amp = ref_stft(x)
    mfcc = sc.mfcc_from_amplitude(amp)
    assert mfcc.shape == (20, amp.shape[1]) and mfcc.dtype == np.float64
    log_mel = 10 * np.log10(np.maximum(ref_mel_bank() @ amp ** 2, 1e-12))
    expect = (ref_dct2_ortho(64) @ log_mel)[:20]
    assert np.allclose(mfcc, expect, rtol=1e-9, atol=1e-9), np.abs(mfcc - expect).max()
    # C0 = sum(log_mel)/sqrt(64)
    assert np.allclose(mfcc[0], log_mel.sum(axis=0) / 8.0, rtol=1e-9, atol=1e-9)
    # 交付的不是 Mel Spectrogram
    assert not np.allclose(mfcc, log_mel[:20], atol=1.0)
    assert np.abs(mfcc - log_mel[:20]).max() > 20
    raises(ValueError, sc.mfcc_from_amplitude, np.ones((64, 10)))


def fit_tone(y, freq, sr=SR, skip=2000):
    """中段對 sin/cos 做最小平方：回傳 (振幅, 殘差 RMS)。頻率不對的話殘差會很大。"""
    t = np.arange(len(y))[skip:-skip] / sr
    basis = np.stack([np.sin(2 * np.pi * freq * t), np.cos(2 * np.pi * freq * t)], axis=1)
    coef = np.linalg.lstsq(basis, y[skip:-skip], rcond=None)[0]
    return float(np.hypot(*coef)), float(np.sqrt(np.mean((y[skip:-skip] - basis @ coef) ** 2)))


def test_6_resampler():
    x = RNG.normal(size=5000)
    same = sc.resample_to_analysis(x, 44100)
    assert same.dtype == np.float64 and np.array_equal(same, x)
    n = 2 * 48000
    for freq in (1000.0, 20000.0):                                      # 通帶內：0 dBFS 進、0 dBFS 出
        y = sc.resample_to_analysis(sine(freq, n, sr=48000), 48000)
        assert y.ndim == 1 and y.dtype == np.float64
        assert abs(len(y) - round(n * 147 / 160)) <= 1, len(y)
        amp, resid = fit_tone(y, freq)
        assert abs(20 * np.log10(amp)) < 0.01, (freq, 20 * np.log10(amp))
        assert resid < 1e-3, (freq, resid)                              # 出來的確實是同一個頻率
    odd = sc.resample_to_analysis(sine(1000.0, 48000 + 77, sr=48000), 48000)
    assert abs(len(odd) - round((48000 + 77) * 147 / 160)) <= 1, len(odd)
    # 23 kHz 高於輸出的 Nyquist（22.05 kHz）：摺回 21.1 kHz 的鏡像至少要壓 60 dB
    y = sc.resample_to_analysis(sine(23000.0, n, sr=48000), 48000)
    alias_db = 20 * np.log10(np.sqrt(2 * np.mean(y[2000:-2000] ** 2)) + 1e-300)
    assert alias_db < -60, alias_db
    e = raises(ValueError, sc.resample_to_analysis, x, 32000)
    assert "32000" in str(e) and not isinstance(e, sc.NoData), e
    raises(ValueError, sc.resample_to_analysis, np.zeros((2, 100)), 44100)


def test_7_analyze_channel():
    # 區間 [1, 2) 秒：前一秒 1 kHz、後一秒 6 kHz，各佔自己的區間
    x = np.concatenate([sine(1000, SR, amp=0.5), sine(6000, SR, amp=0.5), sine(1000, SR, amp=0.5)])
    out = sc.analyze_channel(x, SR, 1.0, 2.0)
    assert set(out) == {"spectrogram_db", "mfcc", "times", "valid_range", "analysis_frames"}
    spec, mfcc, times = out["spectrogram_db"], out["mfcc"], out["times"]
    assert spec.dtype == np.float32 and mfcc.dtype == np.float32 and times.dtype == np.float64
    assert out["analysis_frames"] == 44100 and isinstance(out["analysis_frames"], int)
    assert spec.shape == (N_BINS, 96) and mfcc.shape == (20, 96) and times.shape == (96,)
    assert (spec.argmax(axis=0) == round(6000 / BIN_HZ)).all()           # 沒有混進 1 kHz 的那兩段
    assert np.array_equal(times, 1.0 + np.arange(96) * 441 / 44100)
    assert out["valid_range"] == [times[0], times[-1] + 2048 / 44100]
    assert out["valid_range"][0] == 1.0 and out["valid_range"][1] <= 2.0
    ref = ref_stft(x[44100:88200])
    assert np.array_equal(spec, (20 * np.log10(np.maximum(ref, 1e-6))).astype(np.float32))
    # 端點：樣本 [round(start*44100), round(end*44100))。用白噪音比對，差一個樣本就對不上
    noise = RNG.normal(size=3 * SR)
    got = sc.analyze_channel(noise, SR, 1.0, 2.0)["spectrogram_db"]

    def ref_db(first, last):
        return 20 * np.log10(np.maximum(ref_stft(noise[first:last]), 1e-6))

    assert np.abs(got - ref_db(44100, 88200)).max() < 1e-3
    assert np.abs(got - ref_db(44099, 88199)).max() > 1.0 and np.abs(got - ref_db(44101, 88201)).max() > 1.0
    # end 不含：剛好多一個 hop 才多一個窗
    assert sc.analyze_channel(noise, SR, 1.0, 1.0 + (2048 + 440) / 44100)["spectrogram_db"].shape[1] == 1
    assert sc.analyze_channel(noise, SR, 1.0, 1.0 + (2048 + 441) / 44100)["spectrogram_db"].shape[1] == 2
    # 區間外的訊號不算進來：區間內全零、區間外滿刻度
    z = np.ones(3 * SR)
    z[44100:88200] = 0.0
    assert (sc.analyze_channel(z, SR, 1.0, 2.0)["spectrogram_db"] == -120.0).all()
    # end 省略 = 到結尾；end 超過錄音長度不補資料
    whole = sc.analyze_channel(x, SR)
    assert whole["analysis_frames"] == len(x) and whole["times"][0] == 0.0
    assert whole["spectrogram_db"].shape[1] == 1 + (len(x) - 2048) // 441
    tail = sc.analyze_channel(x, SR, 2.5, 99.0)
    assert tail["analysis_frames"] == len(x) - 110250 and tail["valid_range"][1] <= 3.0
    # 沒有足夠資料
    raises(sc.NoData, sc.analyze_channel, x, SR, 10.0)
    raises(sc.NoData, sc.analyze_channel, x, SR, 3.0)
    raises(sc.NoData, sc.analyze_channel, x, SR, 1.0, 1.0 + 2047 / 44100)
    raises(sc.NoData, sc.analyze_channel, x, SR, 2.0, 1.0)
    assert sc.analyze_channel(x, SR, 1.0, 1.0 + 2048 / 44100)["spectrogram_db"].shape[1] == 1
    raises(ValueError, sc.analyze_channel, x, 32000)
    # 立體聲：左 1 kHz、右 3 kHz（48 kHz 來源），各聲道各自分析，不平均
    n = 2 * 48000
    stereo = np.stack([sine(1000, n, sr=48000, amp=0.5), sine(3000, n, sr=48000, amp=0.5)], axis=1)
    left, right = (sc.analyze_channel(stereo[:, c], 48000) for c in (0, 1))
    assert left["analysis_frames"] == right["analysis_frames"] == 88200
    lbin, rbin = round(1000 / BIN_HZ), round(3000 / BIN_HZ)
    mid = slice(10, -10)
    assert (left["spectrogram_db"][:, mid].argmax(axis=0) == lbin).all()
    assert (right["spectrogram_db"][:, mid].argmax(axis=0) == rbin).all()
    assert lbin != rbin
    for track, own, other in ((left, lbin, rbin), (right, rbin, lbin)):
        level = track["spectrogram_db"][:, mid]
        assert -6.02 - 1.5 < level[own].min() and level[own].max() < -6.02 + 0.05, level[own]   # Hann 最多掉 1.42 dB
        assert level[other].max() < -60, level[other].max()            # 另一個聲道的音沒有滲進來
    assert not np.allclose(left["mfcc"], right["mfcc"], atol=1.0)


def decode(png):
    return mpimg.imread(io.BytesIO(png), format="png")


def test_8_render_and_matrices():
    x = sine(2000, 2 * SR, amp=0.5) + 0.01 * RNG.normal(size=2 * SR)
    out = sc.analyze_channel(x, SR, 0.5, 1.5)
    spec, mfcc, times = out["spectrogram_db"], out["mfcc"], out["times"]
    colour = (float(mfcc.min()), float(mfcc.max()))
    a = render.spectrogram_png(spec, times, (0.0, 2.0), "測試 Left")
    b = render.spectrogram_png(spec, times, (0.0, 4.0), "測試 Left")
    c = render.mfcc_png(mfcc, times, (0.0, 2.0), colour, "測試 Left")
    d = render.mfcc_png(mfcc, times, (0.0, 4.0), colour, "測試 Left")
    images = []
    for png in (a, b, c, d):
        assert isinstance(png, bytes) and png[:8] == PNG_SIGNATURE
        img = decode(png)
        assert img.ndim == 3 and img.shape[0] >= 400 and img.shape[1] >= 400, img.shape
        images.append(img[..., :3])
    assert images[0].shape == images[1].shape and np.abs(images[0] - images[1]).max() > 0.1
    assert images[2].shape == images[3].shape and np.abs(images[2] - images[3]).max() > 0.1
    assert a != c
    # 同樣的輸入畫出同樣的圖；色階範圍不同圖就不同（色階是呼叫端給的，不逐張正規化）
    assert np.array_equal(decode(render.mfcc_png(mfcc, times, (0.0, 2.0), colour, "測試 Left"))[..., :3], images[2])
    wide = decode(render.mfcc_png(mfcc, times, (0.0, 2.0), (colour[0] - 500, colour[1] + 500), "測試 Left"))
    assert np.abs(wide[..., :3] - images[2]).max() > 0.1
    # 資料只佔 [0.5, 1.5)：顯示區間 0..2 秒時，圖的左右兩側不可以被資料填滿
    row = images[0][images[0].shape[0] // 2]
    grey = np.abs(row - np.array([0xd9, 0xd9, 0xd9]) / 255).max(axis=1) < 0.02
    assert 0.25 < grey.mean() < 0.6, grey.mean()
    raises(ValueError, render.spectrogram_png, spec[:, :0], times[:0], (0.0, 2.0), "x")
    raises(ValueError, render.spectrogram_png, spec, times[:-1], (0.0, 2.0), "x")
    raises(ValueError, render.spectrogram_png, spec, times, (2.0, 2.0), "x")
    raises(ValueError, render.mfcc_png, spec, times, (0.0, 2.0), colour, "x")
    # NPZ
    blob = render.matrices_npz(spec, mfcc, times, out["valid_range"])
    assert isinstance(blob, bytes) and blob[:2] == b"PK"
    with np.load(io.BytesIO(blob)) as z:
        assert sorted(z.files) == ["mfcc", "spectrogram", "times", "valid_range"]
        assert z["spectrogram"].shape == (N_BINS, len(times)) and z["spectrogram"].dtype == np.float32
        assert z["mfcc"].shape == (20, len(times)) and z["mfcc"].dtype == np.float32
        assert z["times"].shape == (len(times),) and z["times"].dtype == np.float64
        assert z["valid_range"].shape == (2,) and z["valid_range"].dtype == np.float64
        assert np.array_equal(z["spectrogram"], spec) and np.array_equal(z["mfcc"], mfcc)
        assert np.array_equal(z["times"], times) and z["valid_range"].tolist() == out["valid_range"]
    raises(ValueError, render.matrices_npz, spec, mfcc[:, :-1], times, out["valid_range"])
    raises(ValueError, render.matrices_npz, spec, mfcc, times, [0.0, 1.0, 2.0])


def test_9_parameters():
    p = sc.PARAMETERS
    assert json.loads(json.dumps(p, ensure_ascii=False)) == p
    assert p["fft_size"] == 2048 and p["hop_length"] == 441 and p["analysis_sample_rate"] == 44100
    assert p["mel_bands"] == 64 and p["mfcc_count"] == 20
    assert p["algorithm_version"] == sc.ALGORITHM_VERSION == "mirdc-onprem-track-1"
    assert p["window"] == "periodic Hann" and p["center"] is False and p["dct"] == "II orthonormal"
    assert p["amplitude_floor"] == 1e-6 and p["spectrogram_db_range"] == [-120.0, 0.0]
    assert p["resampler"]["up"] == 147 and p["resampler"]["down"] == 160
    assert p["resampler"]["fir_taps"] == 128 * 160 + 1 and p["resampler"]["kaiser_beta"] == 8.6
    for key in ("amplitude_scaling", "mel", "mfcc", "matrices_format", "padding"):
        assert key in p, key
    assert (sc.ANALYSIS_SAMPLE_RATE, sc.FFT_SIZE, sc.HOP_LENGTH, sc.MEL_BANDS, sc.MFCC_COUNT) == (44100, 2048, 441, 64, 20)
    assert sc.SPECTROGRAM_DB_RANGE == (-120.0, 0.0)


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
