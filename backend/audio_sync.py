"""Opt-in, offline PCM synchronization. No database or web API dependencies.

Inspired by SyncRecord's correlation/alignment approach, implemented independently.
Acoustic offsets include propagation delay; they are NOT device clock offsets.
"""
import argparse
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import re
from uuid import uuid4

import numpy as np
from scipy.io import wavfile
from scipy.signal import correlate, max_len_seq, resample_poly

ANALYSIS_RATE = 48000
PRBS_VERSION = 'cnc-mls10-chip4-v1'


def prbs_signal():
    """Fixed, versioned template. Play only in a dedicated calibration take."""
    return np.repeat(max_len_seq(10)[0].astype(np.float64) * 2 - 1, 4).astype(np.float32) * 0.25


def analysis_copy(samples, rate):
    if type(rate) is not int or not 8000 <= rate <= 384000:
        raise ValueError('invalid actual sample rate')
    x = np.asarray(samples)
    if x.ndim not in (1,2) or (x.ndim==2 and x.shape[1] not in (1,2)) or not len(x) or not np.all(np.isfinite(x)):
        raise ValueError('finite nonempty mono/stereo PCM required')
    if x.dtype.kind == 'i':
        x = x.astype(np.float64) / (2 ** (x.dtype.itemsize * 8 - 1))
    elif x.dtype.kind == 'u':
        x = (x.astype(np.float64) - 128) / 128
    elif x.dtype.kind != 'f':
        raise ValueError('unsupported PCM format')
    ratio = Fraction(ANALYSIS_RATE, rate)
    # 44100 -> 48000 is precisely 160/147, never a header substitution.
    return resample_poly(x, ratio.numerator, ratio.denominator).astype(np.float32)


def detect_prbs(samples, template=None):
    x = np.asarray(samples, dtype=np.float64)
    ref = np.asarray(prbs_signal() if template is None else template, dtype=np.float64)
    if x.ndim != 1 or len(x) < len(ref) or not np.all(np.isfinite(x)):
        raise ValueError('calibration window is empty, short or nonfinite')
    ref = ref - ref.mean()
    energy = np.r_[0., np.cumsum(x*x)]
    sums = np.r_[0., np.cumsum(x)]
    local = energy[len(ref):] - energy[:-len(ref)] - (sums[len(ref):] - sums[:-len(ref)])**2 / len(ref)
    scores = np.abs(correlate(x, ref, mode='valid', method='fft')) / np.sqrt(np.maximum(local, 1e-20) * np.dot(ref, ref))
    peak = int(np.argmax(scores)); confidence = float(min(1., scores[peak]))
    # Ignore only the central correlation lobe; competing arrivals are ambiguous.
    rivals = scores.copy(); rivals[max(0, peak-16):peak+17] = 0
    ratio = confidence / max(float(rivals.max()), 1e-12)
    if confidence < 0.65 or ratio < 1.35:
        raise ValueError('PRBS missing or ambiguous correlation peak')
    return {'sample': peak, 'confidence': confidence, 'peak_ratio': ratio}


def fit_markers(reference, observed):
    a, b = np.asarray(reference, dtype=float), np.asarray(observed, dtype=float)
    if a.shape != b.shape or a.ndim != 1 or not len(a) or not np.all(np.isfinite([a, b])):
        raise ValueError('matching finite calibration markers required')
    if len(a) == 1:
        return float(b[0]-a[0]), 1., None, None
    if len(a) < 3 or a[-1]-a[0] < 5*ANALYSIS_RATE or np.any(np.diff(a)<=0) or np.any(np.diff(b)<=0):
        raise ValueError('drift requires three ordered markers spanning at least five seconds')
    scale = float((b[-1]-b[0])/(a[-1]-a[0])); offset = float(b[0]-scale*a[0])
    residual = float(np.max(np.abs((b[1:-1]-offset)/scale-a[1:-1])))
    if abs(scale-1)>0.002 or residual>ANALYSIS_RATE*0.002:
        raise ValueError('drift model rejected by held-out calibration markers')
    return offset, scale, (scale-1)*1e6, residual


def align_copy(samples, offset, scale=1.):
    if not np.isfinite(offset) or not np.isfinite(scale) or abs(scale-1)>0.002:
        raise ValueError('invalid alignment model')
    ratio = Fraction(1/scale).limit_denominator(100000)
    x = resample_poly(samples, ratio.numerator, ratio.denominator)
    shift = round(offset/scale)
    if abs(shift)>ANALYSIS_RATE*60:
        raise ValueError('offset exceeds 60 second safety limit')
    if shift>=len(x):
        raise ValueError('offset removes the entire track')
    return (x[shift:] if shift>=0 else np.pad(x, ((-shift,0),(0,0)) if x.ndim==2 else (-shift,0))).astype(np.float32)


def contained(root, name):
    path = (root / name).resolve()
    if not path.is_relative_to(root) or path == root:
        raise ValueError('file path outside recording workspace')
    return path


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', value):
        raise ValueError('invalid room/session/device identifier')
    return value


class AudioSyncService:
    def __init__(self, recording_root, *, multiDeviceSyncEnabled=False):
        self.root = Path(recording_root).resolve(strict=True)
        self.enabled = multiDeviceSyncEnabled

    def process(self, manifest):
        if not self.enabled:
            raise ValueError('multiDeviceSyncEnabled is disabled')
        room, session = identifier(manifest['room_code']), identifier(manifest['session_id'])
        mode = manifest.get('mode', 'none')
        if mode not in ('none', 'time', 'prbs'):
            raise ValueError('mode must be none, time or prbs')
        tracks = manifest['tracks']
        if not 1 <= len(tracks) <= 5:
            raise ValueError('one to five independent tracks required')
        loaded = []; seen = set()
        for track in tracks:
            metadata_path = contained(self.root, track['metadata'])
            metadata = json.loads(metadata_path.read_text(encoding='utf-8'))
            device = identifier(metadata['device_id'])
            if device in seen or metadata['room_code'] != room or metadata['session_id'] != session:
                raise ValueError('duplicate device or cross-room/session input')
            seen.add(device)
            path = contained(self.root, track['wav'])
            if path.stat().st_size > 512*1024*1024:
                raise ValueError('offline processing limit is 512 MiB per track')
            rate, raw = wavfile.read(path)
            channels = raw.shape[1] if raw.ndim==2 else 1
            if channels != metadata.get('channel_count',1):
                raise ValueError('WAV and metadata channel counts disagree')
            if rate != metadata['actual_sample_rate'] or len(raw) != metadata['sample_count']:
                raise ValueError('WAV and PCM metadata disagree')
            data = analysis_copy(raw, rate)
            loaded.append((device, metadata, data, {'device_id':device,'original_sample_rate':rate,'analysis_sample_rate':ANALYSIS_RATE,'original_sample_count':len(raw),'analysis_sample_count':len(data),'source_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'offset_samples':None,'offset_ms':None,'drift_ppm':None,'alignment_method':mode,'calibration_status':'unverified','confidence':None}))
        # Each run uses a new namespace. Inputs and previous results are never replaced.
        output = contained(self.root, f'derived/{room}/{session}/{uuid4()}')
        output.mkdir(parents=True, exist_ok=False)
        report = {'room_code':room,'session_id':session,'mode':mode,'status':'unverified','absolute_accuracy':'unverified','propagation_delay':'not separated from acoustic offset','prbs_version':PRBS_VERSION,'tracks':[t[3] for t in loaded]}
        for device, _, data, info in loaded:
            info['channel_count'] = data.shape[1] if data.ndim==2 else 1
            filename = device+'_analysis.wav'
            wavfile.write(output/filename, ANALYSIS_RATE, data)
            info['analysis_file'] = filename
        try:
            if mode == 'none':
                report['reason'] = 'analysis copies only; no alignment requested'
            else:
                if any(m.get('complete') is not True or m.get('sync_status') == 'failed' for _, m, _, _ in loaded):
                    raise ValueError('incomplete capture cannot be verified')
                if len(loaded)<2:
                    raise ValueError('relative alignment requires at least two tracks')
                markers = []
                if mode == 'prbs':
                    # Explicit windows prevent searching CNC process audio for accidental peaks.
                    for track, (_, _, data, info) in zip(tracks, loaded):
                        windows = track.get('calibration_windows', [])
                        if not windows:
                            raise ValueError('explicit calibration windows in seconds are required')
                        hits = []
                        for lo, hi in windows:
                            if not all(math.isfinite(v) for v in (lo,hi)) or not 0 <= lo < hi <= len(data)/ANALYSIS_RATE:
                                raise ValueError('invalid calibration window')
                            start, stop = round(lo*ANALYSIS_RATE), round(hi*ANALYSIS_RATE)
                            channel = track.get('calibration_channel',0)
                            if type(channel) is not int or not 0<=channel<info['channel_count']:
                                raise ValueError('invalid calibration channel')
                            hit = detect_prbs(data[start:stop,channel] if data.ndim==2 else data[start:stop]); hit['sample'] += start; hits.append(hit)
                        info['markers'] = hits; info['confidence'] = min(h['confidence'] for h in hits)
                        markers.append([h['sample'] for h in hits])
                models = []
                for i, (_, metadata, data, info) in enumerate(loaded):
                    if mode == 'prbs':
                        offset, scale, drift, residual = fit_markers(markers[0], markers[i])
                        info.update(drift_ppm=drift,residual_samples=residual,calibration_status='relative_acoustic_only')
                    else:
                        first = loaded[0][1]
                        for m in (first, metadata):
                            if not all(type(m.get(k)) in (float,int) and math.isfinite(m[k]) for k in ('recording_started_at','clock_uncertainty_ms')) or m['clock_uncertainty_ms']<0:
                                raise ValueError('valid clock estimates required for time mode')
                        offset = (first['recording_started_at']-metadata['recording_started_at'])*ANALYSIS_RATE/1000; scale = 1.
                        info['clock_uncertainty_ms'] = first['clock_uncertainty_ms']+metadata['clock_uncertainty_ms']
                    info.update(offset_samples=offset,offset_ms=offset*1000/ANALYSIS_RATE)
                    models.append(align_copy(data, offset, scale))
                length = max(map(len, models))
                for (device, _, _, info), data in zip(loaded, models):
                    filename = device+'_aligned.wav'
                    wavfile.write(output/filename, ANALYSIS_RATE, np.pad(data, ((0,length-len(data)),(0,0)) if data.ndim==2 else (0,length-len(data))))
                    info['aligned_file'] = filename
                report['status'] = 'relative_acoustic_only' if mode=='prbs' else 'time_estimate_unverified'
                report['reason'] = 'Independent aligned copies; zero padding is not measured audio. Absolute accuracy is unverified.'
        except ValueError as error:
            report.update(status='failed',reason=str(error))
            for info in report['tracks']:
                info.update(calibration_status='failed',offset_samples=None,offset_ms=None,drift_ppm=None)
        with (output/'sync-report.json').open('x',encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2, allow_nan=False)
        return output, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True, help='authorized recording workspace')
    parser.add_argument('--manifest', help='JSON path relative to root')
    parser.add_argument('--enable', action='store_true', help='enable multiDeviceSyncEnabled')
    parser.add_argument('--template', action='store_true', help='create PRBS template for a separate calibration take')
    args = parser.parse_args()
    service = AudioSyncService(args.root, multiDeviceSyncEnabled=args.enable)
    if not args.enable:
        parser.error('--enable is required; synchronization is off by default')
    if args.template:
        target = contained(service.root, PRBS_VERSION+'.wav')
        with target.open('xb') as f:
            wavfile.write(f, ANALYSIS_RATE, prbs_signal())
        print(target)
    else:
        if not args.manifest:
            parser.error('--manifest is required')
        manifest = json.loads(contained(service.root,args.manifest).read_text(encoding='utf-8'))
        output, report = service.process(manifest)
        print(json.dumps({'output':str(output),'status':report['status']}))


if __name__ == '__main__':
    main()
