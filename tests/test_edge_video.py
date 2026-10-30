import hashlib
import json
import time
import pytest
from edge.video_jobs import Jobs
from edge.worker import process_job
from edge.runtime import Tracker,source_config,percentile,write_state
from engine.observations3d import assumption_scene
from scripts.make_video_replay import generate


def upload(ledger,data=b'not media',name='video.mp4',mode='inspect'):
    row=ledger.create(name,len(data),['person'],mode)
    ledger.append(row['id'],0,data);return ledger.finish(row['id'])


def test_ledger_resumable_crash_recovery_and_transitions(tmp_path):
    ledger=Jobs(tmp_path);row=ledger.create('clip.mp4',10,['person'])
    ledger.append(row['id'],0,b'12345')
    with ledger.path(row['id']).open('ab') as stream:stream.write(b'crash-orphan')
    with pytest.raises(ValueError):ledger.append(row['id'],0,b'bad')
    ledger.append(row['id'],5,b'67890');assert ledger.path(row['id']).read_bytes()==b'1234567890'
    assert ledger.finish(row['id'])['sha']==hashlib.sha256(b'1234567890').hexdigest()
    assert ledger.claim()==row['id'];ledger.control(row['id'],'pause')
    ledger.control(row['id'],'resume');assert ledger.claim()==row['id']
    ledger.recover();assert ledger.get(row['id'])['state']=='queued'
    ledger.claim();ledger.update(row['id'],model_started=1);ledger.recover()
    assert ledger.get(row['id'])['state']=='failed_or_unknown'
    with pytest.raises(ValueError):ledger.control(row['id'],'retry')
    ledger.control(row['id'],'cancel');assert ledger.delete(row['id'])['deleted']


def test_size_quota_and_retention(tmp_path):
    now=[0.];ledger=Jobs(tmp_path,quota_bytes=20,clock=lambda:now[0])
    row=ledger.create('a.mov',12,['forklift'])
    with pytest.raises(ValueError):ledger.create('b.mov',12,['forklift'])
    with pytest.raises(ValueError):ledger.create('a.html',1,['person'])
    with pytest.raises(ValueError):ledger.create('a.mp4',1,['person,car'])
    with pytest.raises(ValueError):ledger.finish(row['id'])
    now[0]=86401;assert ledger.expire()==1
    with pytest.raises(KeyError):ledger.get(row['id'])


def test_actual_video_content_and_variable_pts(tmp_path):
    pytest.importorskip('av')
    from edge.media import inspect_video
    path=tmp_path/'synthetic.mp4';sidecar=generate(path)
    metadata=inspect_video(path)
    assert metadata['width']==160 and metadata['height']==120
    assert metadata['frame_count']==8 and metadata['variable_frame_intervals']
    assert metadata['frame_timestamps_s'][2]==pytest.approx(.23,abs=.001)
    ledger=Jobs(tmp_path/'ledger');row=upload(ledger,path.read_bytes());assert ledger.claim()==row['id']
    process_job(str(ledger.root),row['id']);done=ledger.get(row['id'])
    assert done['state']=='completed' and done['result']['perception_status']=='NOT_RUN' and done['result']['tracks']==[]
    from integrations.meta.sam import parse_output_text
    from engine.observations3d import sam_tracks
    tracks=sam_tracks(parse_output_text(sidecar['segmentation_text']),metadata['frame_timestamps_s'])['tracks']
    scene=assumption_scene(tracks,.01)
    assert scene['calibration']['status']=='ASSUMPTION_3D'
    assert scene['objects'][0]['provenance']=='ASSUMPTION'


def test_reject_renamed_non_video_and_missing_provider(tmp_path,monkeypatch):
    pytest.importorskip('av')
    ledger=Jobs(tmp_path/'bad');row=upload(ledger);ledger.claim();process_job(str(ledger.root),row['id'])
    assert ledger.get(row['id'])['state']=='failed'
    path=tmp_path/'synthetic.mp4';generate(path);monkeypatch.delenv('MODEL_API_KEY',raising=False)
    ledger=Jobs(tmp_path/'sam');row=upload(ledger,path.read_bytes(),mode='sam_video');ledger.claim();process_job(str(ledger.root),row['id'])
    assert ledger.get(row['id'])['state']=='failed' and not ledger.get(row['id'])['model_started']
    assert 'no synthetic tracks' in ledger.get(row['id'])['error']


def test_source_gate_tracking_and_latency(tmp_path):
    with pytest.raises(ValueError):source_config('rtsp','rtsp://private-camera/live')
    assert source_config('rtsp','rtsp://camera.example/live',['camera.example']).startswith('rtsp:')
    assert source_config('usb','0')==0
    with pytest.raises(ValueError):source_config('usb','20')
    tracker=Tracker();parsed={'frames':[{'records':[{'box':{'x1':0,'x2':10,'y1':0,'y2':10},'confidence':.7}]}]}
    first=tracker.update(parsed,0);second=tracker.update(parsed,.2)
    assert first[0]['object_id']==second[0]['object_id'] and second[0]['kinematics']
    assert tracker.update(parsed,5)[0]['object_id']!=first[0]['object_id']
    assert percentile([1,2,3],.5)==2 and percentile([], .5) is None
    write_state(tmp_path/'live.json',{'physical_actuation':False})
    assert json.loads((tmp_path/'live.json').read_text())['physical_actuation'] is False
