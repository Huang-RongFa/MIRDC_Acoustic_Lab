"""Reproducible, independent-channel STFT and MFCC; never changes source assets."""
from io import BytesIO
from math import gcd
from importlib.metadata import version

import numpy as np
from scipy.signal import get_window, resample_poly, firwin
from scipy.fft import rfft, dct

RATE, FFT, HOP = 44100, 2048, 441
PARAMETERS = dict(analysis_sample_rate=RATE, fft_size=FFT, hop_length=HOP,
                  window='periodic Hann', mel_bands=64, mfcc_count=20,
                  mel_scale='HTK triangular, unit peak', dct='II orthonormal',
                  frequency_range=[0, RATE / 2], spectrogram_scale=[-120, 0],
                  db_reference='20 log10(one-sided peak amplitude / 1.0); Hann coherent-gain normalized; floor -120 dBFS',
                  mfcc_power='squared one-sided peak amplitude; 10 log10(max(mel power, 1e-12)); no per-track reference',
                  frame_policy='center=False; complete windows only; no synthetic end padding',
                  resampling='scipy resample_poly; FIR 128*max(up,down)+1 taps; cutoff=1/max(up,down); Kaiser beta=8.6',
                  time_reference='each recording starts at zero; not sample-synchronized',
                  algorithm_version='v1.4.1')


def package_versions():
    return {name: version(name) for name in ('numpy', 'scipy', 'av', 'matplotlib')}


def decode(source):
    import av
    blocks, rate, channels = [], None, None
    with av.open(source) as container:
        if not container.streams.audio:
            raise ValueError('音檔沒有音訊聲道')
        stream = container.streams.audio[0]
        converter = None
        for frame in container.decode(stream):
            count = len(frame.layout.channels)
            if count not in (1, 2):
                raise ValueError('此版本僅分析實際 Mono 或 Stereo 音檔')
            if rate is None:
                rate, channels = frame.sample_rate, count
                converter = av.AudioResampler(format='fltp', layout=frame.layout, rate=rate)
            if frame.sample_rate != rate or count != channels:
                raise ValueError('音檔途中變更取樣率或聲道數')
            # Convert sample format only: retain the decoder's rate and channel layout.
            for converted in converter.resample(frame):
                blocks.append(converted.to_ndarray())
        if converter:
            blocks.extend(frame.to_ndarray() for frame in converter.resample(None))
    if not blocks:
        raise ValueError('無法解碼有效音訊')
    samples = np.concatenate(blocks, axis=1).astype(np.float64)
    if not np.isfinite(samples).all():
        raise ValueError('音訊包含無效樣本')
    return samples, rate


def resample(samples, rate):
    if rate == RATE:
        return samples.copy()
    divisor = gcd(rate, RATE)
    up, down = RATE // divisor, rate // divisor
    factor = max(up, down)
    lowpass = firwin(128 * factor + 1, 1 / factor, window=('kaiser', 8.6))
    return resample_poly(samples, up, down, window=lowpass)


def mel_filters():
    frequencies = np.fft.rfftfreq(FFT, 1 / RATE)
    mel_edges = np.linspace(0, 2595 * np.log10(1 + RATE / 2 / 700), 66)
    edges = 700 * (10 ** (mel_edges / 2595) - 1)
    rising = (frequencies[None, :] - edges[:-2, None]) / (edges[1:-1] - edges[:-2])[:, None]
    falling = (edges[2:, None] - frequencies[None, :]) / (edges[2:] - edges[1:-1])[:, None]
    return np.maximum(0, np.minimum(rising, falling))


def calculate(samples, rate, start=0., end=None):
    normalized = resample(samples, rate)
    first = int(np.ceil(start * RATE))
    last = min(len(normalized), int(np.floor(end * RATE)) if end is not None else len(normalized))
    selected = normalized[first:last]
    if len(selected) < FFT:
        return None
    windows = np.lib.stride_tricks.sliding_window_view(selected, FFT)[::HOP]
    window = get_window('hann', FFT, fftbins=True)
    # Chunk the FFT intermediate; final matrices stay on the server, never the phone.
    spectrum = np.empty((FFT // 2 + 1, len(windows)))
    coefficients = np.empty((20, len(windows)))
    filters = mel_filters()
    for offset in range(0, len(windows), 2048):
        amplitude = np.abs(rfft(windows[offset:offset + 2048] * window, axis=1)).T / window.sum()
        amplitude[1:-1] *= 2
        spectrum[:, offset:offset + 2048] = 20 * np.log10(np.maximum(amplitude, 1e-6))
        mel_db = 10 * np.log10(np.maximum(filters @ (amplitude ** 2), 1e-12))
        coefficients[:, offset:offset + 2048] = dct(mel_db, type=2, axis=0, norm='ortho')[:20]
    times = (first + np.arange(len(windows)) * HOP + FFT / 2) / RATE
    return dict(spectrogram=spectrum, mfcc=coefficients, times=times,
                valid_range=[first / RATE, (first + (len(windows) - 1) * HOP + FFT) / RATE])


def matrix_file(result):
    output = BytesIO()
    np.savez_compressed(output, **result)
    return output.getvalue()


def render(result, kind, limits, time_range):
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.ticker import FuncFormatter
    figure = Figure(figsize=(8, 4), dpi=120, layout='constrained')
    FigureCanvasAgg(figure)
    axis = figure.subplots()
    values = result[kind]
    # Rendering only: reduce wide images to <=1200 columns by averaging each bin.
    # Lossless numeric matrices are retained separately.
    if values.shape[1] > 1200:
        values = np.stack([part.mean(axis=1) for part in np.array_split(values, 1200, axis=1)], axis=1)
    y_range = [0, RATE / 2] if kind == 'spectrogram' else [-.5, 19.5]
    image = axis.imshow(values, origin='lower', aspect='auto', interpolation='nearest',
                        extent=[*result['valid_range'], *y_range], cmap='magma' if kind == 'spectrogram' else 'coolwarm',
                        vmin=limits[0], vmax=limits[1])
    axis.set(xlim=time_range, ylim=y_range, xlabel='Time (s)', ylabel='Frequency (Hz)' if kind == 'spectrogram' else 'MFCC coefficient')
    formatter = FuncFormatter(lambda value, _: f'{value:.2f}'.rstrip('0').rstrip('.'))
    axis.xaxis.set_major_formatter(formatter)
    if kind == 'mfcc':
        axis.set_yticks(range(20), labels=[f'C{i}' for i in range(20)])
        axis.tick_params(axis='y', labelsize=7)
    else:
        axis.yaxis.set_major_formatter(formatter)
    colorbar = figure.colorbar(image, ax=axis, label='dBFS (peak reference)' if kind == 'spectrogram' else 'MFCC value')
    colorbar.ax.yaxis.set_major_formatter(formatter)
    output = BytesIO()
    figure.savefig(output, format='png')
    figure.clear()
    return output.getvalue()
