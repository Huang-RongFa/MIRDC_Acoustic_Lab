"""把分析矩陣畫成前端直接顯示的 PNG，並匯出 NPZ 數值檔。

每一個 frame 畫在它真正涵蓋的時間 [t, t + hop/sr)；times 中間若有缺口，缺口維持底色，不跨越內插。
時間軸範圍與色階由呼叫端傳入（同一個 run 的所有音軌共用），這裡不逐張正規化。
"""
import io
import threading

import matplotlib

matplotlib.use("Agg")

import numpy as np
from matplotlib import font_manager
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.cm import ScalarMappable
from matplotlib.colors import Normalize
from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter

from . import signal_contract as sc

_CJK_FONTS = ("Microsoft JhengHei", "Microsoft YaHei", "SimHei")
_FIGSIZE, _DPI = (10.0, 4.4), 120            # 1200 x 528 px
_NO_DATA_COLOUR = "#d9d9d9"                  # 顯示區間內沒有分析資料的地方
_FRAME_STEP = sc.HOP_LENGTH / sc.ANALYSIS_SAMPLE_RATE
_N_BINS = sc.FFT_SIZE // 2 + 1
_NYQUIST = sc.ANALYSIS_SAMPLE_RATE / 2
# matplotlib 的 rc_context 改的是整個程序共用的設定。兩個執行緒同時出圖時，一邊還原設定會讓另一邊的中文字型失效
# （2026-11-20 雙執行緒測試實際發生），所以出圖一次只讓一個執行緒做。
_RENDER_LOCK = threading.Lock()


def _fonts():
    installed = {f.name for f in font_manager.fontManager.ttflist}
    cjk = [name for name in _CJK_FONTS if name in installed]
    return cjk + ["DejaVu Sans"], bool(cjk)


def _two_decimals(value, _pos=None):
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return "0" if text in ("-0", "") else text


def _check(matrix, rows, times, time_range, name):
    matrix = np.asarray(matrix)
    times = np.asarray(times, dtype=np.float64)
    if matrix.ndim != 2 or matrix.shape[0] != rows:
        raise ValueError(f"{name} 的形狀必須是 ({rows}, T)，收到 {matrix.shape}")
    if times.ndim != 1 or times.shape[0] != matrix.shape[1]:
        raise ValueError(f"times 的長度（{times.shape}）與 {name} 的 frame 數（{matrix.shape[1]}）不一致")
    if matrix.shape[1] == 0:
        raise ValueError(f"{name} 沒有任何 frame，不產生空白圖")
    t0, t1 = (float(v) for v in time_range)
    if not (np.isfinite(t0) and np.isfinite(t1) and t1 > t0):
        raise ValueError(f"time_range 必須是 (起, 迄) 且迄大於起，收到 {time_range!r}")
    return matrix, times, (t0, t1)


def _contiguous_runs(times):
    """把 frame 依時間連續性分段；相鄰 frame 間隔不是一個 hop 的地方就是分段點。"""
    gaps = np.flatnonzero(np.abs(np.diff(times) - _FRAME_STEP) > _FRAME_STEP * 0.01) + 1
    return np.split(np.arange(times.shape[0]), gaps)


def _draw(matrix, times, time_range, y_extent, norm, cmap, title, x_label, y_label, bar_label, finish_axes=None):
    fonts, _ = _fonts()
    rc = {"font.family": "sans-serif", "font.sans-serif": fonts, "axes.unicode_minus": False}
    with _RENDER_LOCK, matplotlib.rc_context(rc):
        fig = Figure(figsize=_FIGSIZE, dpi=_DPI, layout="constrained")
        FigureCanvasAgg(fig)
        ax = fig.add_subplot()
        ax.set_facecolor(_NO_DATA_COLOUR)
        for run in _contiguous_runs(times):
            ax.imshow(matrix[:, run], origin="lower", aspect="auto", cmap=cmap, norm=norm,
                      extent=(times[run[0]], times[run[-1]] + _FRAME_STEP, y_extent[0], y_extent[1]))
        ax.set_xlim(*time_range)
        ax.set_xlabel(x_label)
        ax.set_ylabel(y_label)
        ax.xaxis.set_major_formatter(FuncFormatter(_two_decimals))
        if finish_axes is not None:
            finish_axes(ax)
        if title:
            ax.set_title(str(title))
        bar = fig.colorbar(ScalarMappable(norm=norm, cmap=cmap), ax=ax, pad=0.02)
        bar.set_label(bar_label)
        bar.ax.yaxis.set_major_formatter(FuncFormatter(_two_decimals))
        out = io.BytesIO()
        fig.savefig(out, format="png")
    return out.getvalue()


def spectrogram_png(spectrogram_db, times, time_range, title):
    matrix, times, time_range = _check(spectrogram_db, _N_BINS, times, time_range, "spectrogram_db")
    cjk = _fonts()[1]
    half_bin = sc.ANALYSIS_SAMPLE_RATE / sc.FFT_SIZE / 2

    def finish(ax):
        ax.set_ylim(0.0, _NYQUIST)
        ax.yaxis.set_major_formatter(FuncFormatter(_two_decimals))

    return _draw(matrix, times, time_range, (-half_bin, _NYQUIST + half_bin),
                 Normalize(*sc.SPECTROGRAM_DB_RANGE), "magma", title,
                 "時間 (s)" if cjk else "Time (s)", "頻率 (Hz)" if cjk else "Frequency (Hz)", "dBFS", finish)


def mfcc_png(mfcc, times, time_range, color_range, title):
    matrix, times, time_range = _check(mfcc, sc.MFCC_COUNT, times, time_range, "mfcc")
    low, high = (float(v) for v in color_range)
    if not (np.isfinite(low) and np.isfinite(high) and high >= low):
        raise ValueError(f"color_range 必須是 (最小, 最大)，收到 {color_range!r}")
    if high == low:                           # 整個 run 只有單一數值時色階仍要畫得出來
        low, high = low - 1.0, high + 1.0
    cjk = _fonts()[1]

    def finish(ax):
        ax.set_ylim(-0.5, sc.MFCC_COUNT - 0.5)
        ax.set_yticks(range(sc.MFCC_COUNT))
        ax.set_yticklabels([f"C{i}" for i in range(sc.MFCC_COUNT)], fontsize=8)

    return _draw(matrix, times, time_range, (-0.5, sc.MFCC_COUNT - 0.5), Normalize(low, high), "viridis", title,
                 "時間 (s)" if cjk else "Time (s)", "MFCC 係數" if cjk else "MFCC coefficient", "MFCC", finish)


def matrices_npz(spectrogram_db, mfcc, times, valid_range):
    spectrogram = np.asarray(spectrogram_db)
    mfcc = np.asarray(mfcc)
    times = np.asarray(times, dtype=np.float64)
    valid_range = np.asarray(valid_range, dtype=np.float64)
    if spectrogram.ndim != 2 or spectrogram.shape[0] != _N_BINS:
        raise ValueError(f"spectrogram 的形狀必須是 ({_N_BINS}, T)，收到 {spectrogram.shape}")
    frame_count = spectrogram.shape[1]
    if mfcc.shape != (sc.MFCC_COUNT, frame_count):
        raise ValueError(f"mfcc 的形狀必須是 ({sc.MFCC_COUNT}, {frame_count})，收到 {mfcc.shape}")
    if times.shape != (frame_count,):
        raise ValueError(f"times 的形狀必須是 ({frame_count},)，收到 {times.shape}")
    if valid_range.shape != (2,):
        raise ValueError(f"valid_range 必須是兩個數值，收到形狀 {valid_range.shape}")
    out = io.BytesIO()
    np.savez_compressed(out, spectrogram=spectrogram, mfcc=mfcc, times=times, valid_range=valid_range)
    return out.getvalue()
