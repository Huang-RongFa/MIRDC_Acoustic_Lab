"""外部音訊分析的數值核心：每個聲道各自的 Spectrogram 與 MFCC。

定義來自對接規格第 8 節「分析參數契約」，並和網站內建分析 backend/analysis_signal.py（v1.4.1）逐項對過數值
（tests/test_track_reference.py）。逐項對應如下（改任何一項都必須換 ALGORITHM_VERSION）：

  分析取樣率   44100 Hz；來源 44100 原樣使用，其他取樣率以 polyphase 重取樣（48000 即 147/160）
  STFT         FFT 2048、hop 441、periodic Hann、center=False、只算完整窗、不補任何訊號
  區間         樣本 [ceil(start*44100), min(總長, floor(end*44100)))；每個窗的時間記在窗的中心
  振幅尺度     |FFT| / sum(window)；DC 與 Nyquist 以外的頻點乘 2（峰值 1.0 的正弦 = 0 dBFS，非校正聲壓）
  Spectrogram  20*log10(max(amplitude, 1e-6))，範圍固定 -120..0 dBFS
  Mel          64 個三角濾波器、HTK 轉換、0..22050 Hz、66 個等距 mel 點、三角形頂點高度 1（不做面積正規化）
  MFCC         amplitude**2 -> Mel -> 10*log10(max(power, 1e-12)) -> DCT-II orthonormal -> C0..C19

只依賴 numpy / scipy；不讀寫資料庫，也不畫圖（畫圖在 render.py）。
"""
import math
from functools import lru_cache

import numpy as np
import scipy.fft
import scipy.signal

ANALYSIS_SAMPLE_RATE = 44100
FFT_SIZE = 2048
HOP_LENGTH = 441
MEL_BANDS = 64
MFCC_COUNT = 20
SPECTROGRAM_DB_RANGE = (-120.0, 0.0)
ALGORITHM_VERSION = "mirdc-onprem-track-2"

_N_BINS = FFT_SIZE // 2 + 1                 # 1025
_AMPLITUDE_FLOOR = 1e-6                     # -120 dBFS
_MEL_POWER_FLOOR = 1e-12                    # -120 dB
_RESAMPLE_TAPS_PER_FACTOR = 128             # FIR 長度 = 128 * max(up, down) + 1
# 重取樣比例 up/down 兩個數字的上限。常見取樣率（8000～384000 Hz）最大只到 1280（384000 Hz 是 147/1280）。
# 沒有上限的話，一個取樣率很怪的檔案（例如 2000003 Hz）會要求幾 GB 的濾波器，1 Hz 會把每個樣本放大成 44100 個。
MAX_RESAMPLE_FACTOR = 2048
_RESAMPLE_KAISER_BETA = 8.6
_STFT_CHUNK_FRAMES = 2048                   # 一次做幾個窗的 FFT；只影響記憶體用量，不影響結果

# 寫進 result.parameters。前 16 個鍵和網站內建分析（analysis_signal.PARAMETERS）同名、同型別，
# 讓前端不管讀到哪一邊的結果都看得懂；後面是地端補充的說明。全部是單層，值只有數字、字串或數字清單。
PARAMETERS = {
    "analysis_sample_rate": ANALYSIS_SAMPLE_RATE,
    "fft_size": FFT_SIZE,
    "hop_length": HOP_LENGTH,
    "window": "periodic Hann",
    "mel_bands": MEL_BANDS,
    "mfcc_count": MFCC_COUNT,
    "mel_scale": "HTK triangular, unit peak",
    "dct": "II orthonormal",
    "frequency_range": [0, ANALYSIS_SAMPLE_RATE / 2],
    "spectrogram_scale": [int(SPECTROGRAM_DB_RANGE[0]), int(SPECTROGRAM_DB_RANGE[1])],
    "db_reference": "20 log10(one-sided peak amplitude / 1.0); Hann coherent-gain normalized; floor -120 dBFS",
    "mfcc_power": "squared one-sided peak amplitude; 10 log10(max(mel power, 1e-12)); no per-track reference",
    "frame_policy": "center=False; complete windows only; no synthetic end padding",
    "resampling": "scipy resample_poly; FIR 128*max(up,down)+1 taps; cutoff=1/max(up,down); Kaiser beta=8.6",
    "time_reference": "each recording starts at zero; not sample-synchronized",
    "algorithm_version": ALGORITHM_VERSION,
    # ── 地端補充 ──
    "channels": "each decoded channel analysed on its own; no downmix, no averaging",
    "interval_samples": "first = ceil(start_seconds * 44100); last = min(total, floor(end_seconds * 44100))",
    "frame_time": "window centre in recording seconds: (first + k * hop_length + fft_size / 2) / 44100",
    "valid_range": "[first / 44100, (first + (T - 1) * hop_length + fft_size) / 44100]",
    "resample_limit": "sources whose up or down factor exceeds 2048 are rejected as a source error",
    "decoder": "ffmpeg command line to 32-bit float PCM at the decoded sample rate and channel count",
    "matrices_format": "NPZ (numpy.savez_compressed): spectrogram float32 (1025, T) dBFS; mfcc float32 (20, T); "
                       "times float64 (T,); valid_range float64 (2,)",
}


class NoData(Exception):
    """要求的區間裡不足一個完整窗（2048 個 44100 Hz 樣本）。"""


def _as_channel(x):
    x = np.asarray(x, dtype=np.float64)
    if x.ndim != 1:
        raise ValueError(f"需要單一聲道的一維陣列，收到的形狀是 {x.shape}")
    return x


def resample_ratio(sample_rate):
    """(up, down)：sample_rate * up / down = 44100。算法和網站內建分析相同；地端另外設了比例上限（內建沒有）。"""
    if isinstance(sample_rate, bool) or not isinstance(sample_rate, (int, np.integer)) or sample_rate <= 0:
        raise ValueError(f"取樣率必須是正整數，收到 {sample_rate!r}")
    divisor = math.gcd(int(sample_rate), ANALYSIS_SAMPLE_RATE)
    up, down = ANALYSIS_SAMPLE_RATE // divisor, int(sample_rate) // divisor
    if max(up, down) > MAX_RESAMPLE_FACTOR:
        raise ValueError(f"取樣率 {int(sample_rate)} Hz 換算到 44100 Hz 的比例是 {up}/{down}，超過地端的處理上限 {MAX_RESAMPLE_FACTOR}")
    return up, down


@lru_cache(maxsize=4)
def _resample_taps(up, down):
    # firwin 的直流增益是 1；resample_poly 會自己把係數乘上 up，所以這裡不能再乘，
    # 否則通帶會多出 20*log10(up) dB（tests/test_track_signal.py 以 0 dBFS 正弦實測）。
    factor = max(up, down)
    taps = scipy.signal.firwin(_RESAMPLE_TAPS_PER_FACTOR * factor + 1, 1.0 / factor,
                               window=("kaiser", _RESAMPLE_KAISER_BETA))
    taps.setflags(write=False)
    return taps


def resample_to_analysis(x, sample_rate):
    """一維 float64 進、一維 float64（44100 Hz）出。"""
    x = _as_channel(x)
    up, down = resample_ratio(sample_rate)
    if up == down:
        return x.copy()
    return scipy.signal.resample_poly(x, up, down, window=_resample_taps(up, down))


@lru_cache(maxsize=1)
def _window():
    w = scipy.signal.get_window("hann", FFT_SIZE, fftbins=True)
    w.setflags(write=False)
    return w


def stft_amplitude(x):
    """x 為 44100 Hz。回傳 (amplitude float64 (1025, T), times float64 (T,))，times 為各窗中心相對於 x 開頭的秒數。"""
    x = _as_channel(x)
    n = x.shape[0]
    if n < FFT_SIZE:
        raise NoData(f"只有 {n} 個樣本，不足一個完整窗（{FFT_SIZE}）")
    frame_count = 1 + (n - FFT_SIZE) // HOP_LENGTH
    window = _window()
    # 每 hop 取一個完整窗；尾端湊不滿一窗的樣本不使用，也不補值
    frames = np.lib.stride_tricks.sliding_window_view(x, FFT_SIZE)[::HOP_LENGTH]
    amplitude = np.empty((_N_BINS, frame_count), dtype=np.float64)
    for first in range(0, frame_count, _STFT_CHUNK_FRAMES):
        block = frames[first:first + _STFT_CHUNK_FRAMES] * window
        amplitude[:, first:first + block.shape[0]] = np.abs(scipy.fft.rfft(block, axis=1)).T
    amplitude /= window.sum()
    amplitude[1:-1] *= 2.0                   # 單邊頻譜：DC 與 Nyquist 沒有鏡像，不乘
    times = (np.arange(frame_count) * HOP_LENGTH + FFT_SIZE / 2) / ANALYSIS_SAMPLE_RATE
    return amplitude, times


def spectrogram_db(amplitude):
    return 20.0 * np.log10(np.maximum(np.asarray(amplitude, dtype=np.float64), _AMPLITUDE_FLOOR))


def _hz_to_mel(hz):
    return 2595.0 * np.log10(1.0 + np.asarray(hz, dtype=np.float64) / 700.0)


def _mel_to_hz(mel):
    return 700.0 * (10.0 ** (np.asarray(mel, dtype=np.float64) / 2595.0) - 1.0)


@lru_cache(maxsize=1)
def _mel_filterbank():
    f_max = ANALYSIS_SAMPLE_RATE / 2
    points = _mel_to_hz(np.linspace(0.0, _hz_to_mel(f_max), MEL_BANDS + 2))
    points[0], points[-1] = 0.0, f_max       # 兩端點不留浮點誤差
    freqs = np.arange(_N_BINS) * ANALYSIS_SAMPLE_RATE / FFT_SIZE
    low, centre, high = points[:-2, None], points[1:-1, None], points[2:, None]
    rising = (freqs - low) / (centre - low)
    falling = (high - freqs) / (high - centre)
    bank = np.maximum(0.0, np.minimum(rising, falling))
    bank.setflags(write=False)
    return bank


def mel_filterbank():
    """(64, 1025)。三角形頂點高度為 1，取值在 FFT 頻點上（頂點通常落在兩個頻點之間）。"""
    return _mel_filterbank().copy()


def mfcc_from_amplitude(amplitude):
    amplitude = np.asarray(amplitude, dtype=np.float64)
    if amplitude.ndim != 2 or amplitude.shape[0] != _N_BINS:
        raise ValueError(f"amplitude 的形狀必須是 ({_N_BINS}, T)，收到 {amplitude.shape}")
    mel_power = _mel_filterbank() @ (amplitude ** 2)
    log_mel = 10.0 * np.log10(np.maximum(mel_power, _MEL_POWER_FLOOR))
    return scipy.fft.dct(log_mel, type=2, norm="ortho", axis=0)[:MFCC_COUNT]


def analyze_channel(x, sample_rate, start_seconds=0.0, end_seconds=None):
    """單一聲道（解碼後的原始取樣率）在錄音時間 [start_seconds, end_seconds) 內的分析結果。"""
    start_seconds = float(start_seconds)
    if not np.isfinite(start_seconds) or start_seconds < 0:
        raise ValueError(f"start_seconds 必須是不小於 0 的有限數值，收到 {start_seconds}")
    if end_seconds is not None:
        end_seconds = float(end_seconds)
        if np.isnan(end_seconds):
            raise ValueError("end_seconds 不可以是 NaN")
    y = resample_to_analysis(x, sample_rate)
    total = y.shape[0]
    # 區間端點和網站內建分析一致：起點往後取整、終點往前取整，不會用到區間以外的樣本
    first = int(math.ceil(start_seconds * ANALYSIS_SAMPLE_RATE))
    last = total if end_seconds is None or np.isinf(end_seconds) else int(math.floor(end_seconds * ANALYSIS_SAMPLE_RATE))
    last = min(last, total)                  # 超出錄音長度的部分沒有資料，不補
    frames_in_interval = max(0, last - first)
    if frames_in_interval < FFT_SIZE:
        raise NoData(f"區間 [{start_seconds}, {end_seconds}) 秒內只有 {frames_in_interval} 個 44100 Hz 樣本，"
                     f"不足一個完整窗（{FFT_SIZE}）；錄音共 {total / ANALYSIS_SAMPLE_RATE:.3f} 秒")
    amplitude, _ = stft_amplitude(y[first:last])
    frame_count = amplitude.shape[1]
    times = (first + np.arange(frame_count) * HOP_LENGTH + FFT_SIZE / 2) / ANALYSIS_SAMPLE_RATE
    return {
        "spectrogram_db": spectrogram_db(amplitude).astype(np.float32),
        "mfcc": mfcc_from_amplitude(amplitude).astype(np.float32),
        "times": times,
        "valid_range": [first / ANALYSIS_SAMPLE_RATE,
                        (first + (frame_count - 1) * HOP_LENGTH + FFT_SIZE) / ANALYSIS_SAMPLE_RATE],
        "analysis_frames": int(frames_in_interval),
    }
