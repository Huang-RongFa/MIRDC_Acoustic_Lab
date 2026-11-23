import hashlib
import json

import numpy as np
import pytest
from scipy.io import wavfile
from scipy.signal import resample_poly

from backend.audio_sync import AudioSyncService, analysis_copy, align_copy, detect_prbs, fit_markers, prbs_signal


@pytest.mark.parametrize('rate', [44100, 48000])
def test_actual_rate_conversion_preserves_duration_and_pitch(rate):
    t = np.arange(rate*2)/rate
    raw = np.sin(2*np.pi*1000*t).astype(np.float32)
    before = raw.copy(); result = analysis_copy(raw, rate)
    assert len(result) == 96000
    assert np.array_equal(raw, before)
    assert abs(np.fft.rfftfreq(len(result), 1/48000)[np.argmax(abs(np.fft.rfft(result)))]-1000)<1


def test_prbs_known_offsets_and_residual():
    template = prbs_signal()
    ref = np.pad(template, (1500, 5000)); shifted = np.pad(template, (1980, 4520))
    a, b = detect_prbs(ref), detect_prbs(shifted)
    assert b['sample']-a['sample'] == 480
    aligned = align_copy(shifted, 480)
    assert detect_prbs(aligned)['sample']-a['sample'] == 0


@pytest.mark.parametrize('data', [np.zeros(10000), np.sin(np.arange(10000)*0.2), np.r_[prbs_signal(),np.zeros(500),prbs_signal()]])
def test_reject_missing_and_ambiguous_prbs(data):
    with pytest.raises(ValueError,match='missing or ambiguous'):
        detect_prbs(data)


def test_long_clock_drift_requires_independent_evidence():
    reference = np.array([48000.,48000*300.,48000*600.])
    observed = 320 + reference*1.00012
    offset, scale, drift, residual = fit_markers(reference, observed)
    assert offset == pytest.approx(320)
    assert drift == pytest.approx(120)
    assert residual < 1e-7
    assert scale == pytest.approx(1.00012)
    with pytest.raises(ValueError,match='held-out'):
        fit_markers(reference, observed+np.array([0,1000,0]))
    with pytest.raises(ValueError,match='three ordered'):
        fit_markers(reference[:2], observed[:2])
    assert fit_markers(reference[:1],observed[:1])[2] is None


def make_manifest(root, rates=(48000,44100), mode='prbs', missing=False):
    tracks=[]
    for i, rate in enumerate(rates):
        x=np.zeros(48000*2,dtype=np.float32)
        start=12000+i*480
        if not missing:x[start:start+len(prbs_signal())]=prbs_signal()
        raw=resample_poly(x,147,160).astype(np.float32) if rate==44100 else x
        name=f'device{i}'
        wavfile.write(root/(name+'.wav'),rate,raw)
        metadata={'room_code':'ROOM01','session_id':'session1','device_id':name,'actual_sample_rate':rate,'sample_count':len(raw),'complete':True,'recording_started_at':100000-i*10,'clock_uncertainty_ms':5}
        (root/(name+'.json')).write_text(json.dumps(metadata),encoding='utf-8')
        tracks.append({'wav':name+'.wav','metadata':name+'.json','calibration_windows':[[0,1]]})
    return {'room_code':'ROOM01','session_id':'session1','mode':mode,'tracks':tracks}


def test_mixed_rate_service_preserves_originals_and_retries(tmp_path):
    manifest=make_manifest(tmp_path)
    hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in tmp_path.iterdir()}
    service=AudioSyncService(tmp_path,multiDeviceSyncEnabled=True)
    output,report=service.process(manifest)
    assert report['status']=='relative_acoustic_only'
    assert report['absolute_accuracy']=='unverified'
    assert report['tracks'][1]['offset_samples']==pytest.approx(480,abs=1)
    assert report['tracks'][1]['drift_ppm'] is None
    waves=[wavfile.read(output/t['aligned_file'])[1] for t in report['tracks']]
    assert len(waves[0])==len(waves[1])
    assert abs(detect_prbs(waves[0])['sample']-detect_prbs(waves[1])['sample'])<=1
    again,_=service.process(manifest)
    assert again!=output
    for name,digest in hashes.items():assert hashlib.sha256((tmp_path/name).read_bytes()).hexdigest()==digest


def test_failed_sync_keeps_analysis_copies_and_raw(tmp_path):
    manifest=make_manifest(tmp_path,missing=True)
    output,report=AudioSyncService(tmp_path,multiDeviceSyncEnabled=True).process(manifest)
    assert report['status']=='failed'
    assert not list(output.glob('*_aligned.wav'))
    assert len(list(output.glob('*_analysis.wav')))==2
    assert (tmp_path/'device0.wav').exists()


@pytest.mark.parametrize('mode,status', [('none','unverified'),('time','time_estimate_unverified')])
def test_uncalibrated_modes_never_claim_precision(tmp_path,mode,status):
    manifest=make_manifest(tmp_path,mode=mode)
    _,report=AudioSyncService(tmp_path,multiDeviceSyncEnabled=True).process(manifest)
    assert report['status']==status
    assert all(t['calibration_status']=='unverified' for t in report['tracks'])


def test_default_disabled_and_workspace_boundaries(tmp_path):
    manifest=make_manifest(tmp_path)
    with pytest.raises(ValueError,match='disabled'):AudioSyncService(tmp_path).process(manifest)
    service=AudioSyncService(tmp_path,multiDeviceSyncEnabled=True)
    manifest['tracks'][0]['wav']='../outside.wav'
    with pytest.raises(ValueError,match='outside'):service.process(manifest)


@pytest.mark.parametrize('field,value', [('actual_sample_rate',48000),('sample_count',1),('session_id','another')])
def test_reject_inconsistent_metadata(tmp_path,field,value):
    manifest=make_manifest(tmp_path)
    path=tmp_path/'device1.json'; metadata=json.loads(path.read_text());metadata[field]=value;path.write_text(json.dumps(metadata))
    with pytest.raises(ValueError):AudioSyncService(tmp_path,multiDeviceSyncEnabled=True).process(manifest)


def test_real_resampling_corrects_measured_drift():
    x=np.zeros(48000*8,dtype=np.float32)
    for start in [48000,48000*4,48000*7]:x[start:start+len(prbs_signal())]=prbs_signal()
    y=np.pad(resample_poly(x,10001,10000),(320,0))
    starts=[48000,48000*4,48000*7]
    a=[detect_prbs(x[s-100:s+6000])['sample']+s-100 for s in starts]
    b=[detect_prbs(y[s-100:s+6000])['sample']+s-100 for s in starts]
    offset,scale,drift,_=fit_markers(a,b)
    assert drift==pytest.approx(100,abs=4)
    corrected=align_copy(y,offset,scale)
    for s in starts:assert abs(detect_prbs(corrected[s-100:s+6000])['sample']-100)<=2
