from io import BytesIO
import wave

import numpy as np
import pytest
from scipy.fft import dct

from backend.analysis_signal import RATE, FFT, calculate, decode, mel_filters, resample, render


def wav_bytes(rate, frequencies, seconds=.3):
    time = np.arange(int(rate * seconds)) / rate
    samples = np.stack([.4 * np.sin(2 * np.pi * f * time) for f in frequencies], axis=1)
    output = BytesIO()
    with wave.open(output, 'wb') as wav:
        wav.setparams((len(frequencies), 2, rate, 0, 'NONE', 'not compressed'))
        wav.writeframes((samples * 32767).astype('<i2').tobytes())
    return output.getvalue()


@pytest.mark.parametrize('rate', [44100,48000])
@pytest.mark.parametrize('frequencies', [[1000],[1000,4000]])
def test_actual_decode_and_independent_channels(rate, frequencies):
    samples, actual = decode(BytesIO(wav_bytes(rate, frequencies)))
    assert actual == rate and samples.shape == (len(frequencies), int(rate * .3))
    for channel, frequency in zip(samples, frequencies):
        result = calculate(channel, actual)
        peak = np.argmax(result['spectrogram'].mean(axis=1)) * RATE / FFT
        assert abs(peak - frequency) < RATE / FFT
        assert result['mfcc'].shape[0] == 20


def test_fixed_db_reference_and_real_dct():
    signal = np.sin(2*np.pi*100*np.arange(RATE)/FFT)
    full, half = calculate(signal, RATE), calculate(signal*.5, RATE)
    assert full['spectrogram'][100,10] == pytest.approx(0, abs=1e-8)
    assert half['spectrogram'][100,10] == pytest.approx(-6.0206, abs=1e-4)
    # Analytic Hann-window spectrum of this bin-centered unit sine.
    power = np.zeros(FFT//2+1)
    power[99:102] = [.25,1,.25]
    expected = dct(10*np.log10(np.maximum(mel_filters() @ power,1e-12)),type=2,norm='ortho')[:20]
    np.testing.assert_allclose(full['mfcc'][:,0], expected, atol=1e-8)
    assert not np.array_equal(full['mfcc'], half['mfcc'])


def test_antialias_and_source_unchanged():
    t = np.arange(48000) / 48000
    source = np.sin(2*np.pi*23900*t)
    original = source.copy()
    target = resample(source,48000)
    assert len(target) == RATE
    assert np.sqrt(np.mean(target[1000:-1000]**2)) < .01
    np.testing.assert_array_equal(source, original)


def test_range_silence_short_and_invalid():
    result = calculate(np.zeros(RATE), RATE, .2, .5)
    assert np.isfinite(result['mfcc']).all()
    assert result['valid_range'][0] == .2 and result['valid_range'][1] <= .5
    assert calculate(np.zeros(100),RATE) is None
    assert calculate(np.zeros(RATE),RATE,2,3) is None
    with pytest.raises(Exception):
        decode(BytesIO(b'not audio'))
    png = render(result,'mfcc',[-1000,100],[0,2])
    assert png.startswith(b'\x89PNG\r\n\x1a\n')
