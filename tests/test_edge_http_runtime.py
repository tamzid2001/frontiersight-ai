import json
import os
from pathlib import Path
import queue
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from types import SimpleNamespace
import sys
import pytest
from edge.server import Handler,serve
from edge.video_jobs import Jobs
from edge.runtime import acquire,run,_put_latest
from edge.worker import Supervisor
from integrations.ros2_shadow import snapshot
from scripts.make_video_replay import generate


@pytest.fixture
def edge_http(tmp_path):
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    server.token='fixture-test-operator-'+'x'*32;server.origins={'https://frontiersight-ai.vercel.app'};server.ledger=Jobs(tmp_path)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    def request(path,data=None,headers=None,method=None):
        all_headers={'Authorization':'Bearer '+server.token,'Content-Type':'application/json',**(headers or {})}
        encoded=data if isinstance(data,bytes) else json.dumps(data).encode() if data is not None else None
        with urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:'+str(server.server_port)+path,data=encoded,headers=all_headers,method=method)) as response:
            return response.status,json.load(response) if response.status!=204 else None
    yield request,server.ledger
    server.shutdown();server.server_close();thread.join()


def test_authenticated_edge_http_mcp_and_upload_offsets(edge_http):
    request,ledger=edge_http
    assert request('/health')[1]['physical_actuation'] is False
    with pytest.raises(urllib.error.HTTPError) as e:request('/health',headers={'Authorization':'Bearer bad'})
    assert e.value.code==401
    with pytest.raises(urllib.error.HTTPError) as e:request('/health',headers={'Origin':'https://evil.invalid'})
    assert e.value.code==403
    assert request('/state')[1]['fresh'] is False
    assert len(request('/mcp',{'jsonrpc':'2.0','id':1,'method':'tools/list'})[1]['result']['tools'])==2
    assert request('/mcp',{'jsonrpc':'2.0','id':1,'method':'initialize'})[1]['result']['protocolVersion']=='2025-11-25'
    assert request('/mcp',{'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':'inspect_live_session'}})[1]['result']['structuredContent']['fresh'] is False
    row=request('/uploads',{'name':'fixture.mp4','size':3,'concepts':['person'],'mode':'inspect'})[1]
    identity=row['id'];request('/jobs/'+identity+'/chunk',b'123',{'Upload-Offset':'0'})
    assert request('/jobs/'+identity+'/finish',{})[1]['state']=='queued'
    assert request('/jobs/'+identity+'/pause',{})[1]['state']=='paused'
    assert request('/jobs/'+identity+'/resume',{})[1]['state']=='queued'
    assert request('/jobs/'+identity+'/cancel',{})[1]['state']=='cancelled'
    assert request('/jobs/'+identity+'/delete',{})[1]['deleted']
    with pytest.raises(urllib.error.HTTPError):request('/jobs/'+identity)
    assert request('/health',headers={'Origin':'https://frontiersight-ai.vercel.app'},method='OPTIONS')[0]==204
    with pytest.raises(urllib.error.HTTPError):request('/health',headers={'Origin':'https://evil.invalid'},method='OPTIONS')
    with pytest.raises(urllib.error.HTTPError):request('/bad',{})
    with pytest.raises(ValueError):serve('/not-used',host='0.0.0.0')


def test_replay_runtime_runs_real_decoder_and_emits_freshness(tmp_path):
    pytest.importorskip('av');path=tmp_path/'source.mp4';generate(path)
    target=tmp_path/'state.json'
    state=run('file',str(path),target,fps=30,frames=4)
    assert state['metrics']['processed_frames']==4
    assert state['metrics']['inference_latency_ms']['0.5'] is None
    assert state['perception_status']=='NOT_RUN' and not state['physical_actuation'] and state['stale']
    assert snapshot(target)['poses']==[]
    assert json.loads(target.read_text())['timestamp_kind']=='media_pts'


def test_real_file_acquisition_queue_backpressure(tmp_path):
    pytest.importorskip('av');path=tmp_path/'source.mp4';generate(path)
    channel=queue.Queue(maxsize=1);stop=SimpleNamespace(is_set=lambda:False,wait=lambda seconds:False)
    acquire('file',str(path),channel,stop,30)
    assert channel.get()['end'] is True  # latest-item policy remains bounded
    assert _put_latest(queue.Queue(maxsize=1),{'index':0})==0


def test_camera_error_cleanup_is_a_unit_fixture_not_hardware(monkeypatch):
    released=[]
    class Capture:
        def open(self,*args):return False
        def release(self):released.append(True)
    monkeypatch.setitem(sys.modules,'cv2',SimpleNamespace(VideoCapture=Capture,CAP_PROP_OPEN_TIMEOUT_MSEC=1,CAP_PROP_READ_TIMEOUT_MSEC=2,CAP_FFMPEG=3))
    channel=queue.Queue();stop=SimpleNamespace(is_set=lambda:False)
    acquire('usb',0,channel,stop)
    assert released and channel.get()['error']=='source_disconnected_or_decode_failed'


def test_supervisor_executes_durable_inspection_in_child(tmp_path):
    pytest.importorskip('av');path=tmp_path/'source.mp4';generate(path)
    ledger=Jobs(tmp_path/'ledger');payload=path.read_bytes();row=ledger.create('video.mp4',len(payload),['person'])
    ledger.append(row['id'],0,payload);ledger.finish(row['id'])
    supervisor=Supervisor(ledger);thread=threading.Thread(target=supervisor.run);thread.start()
    try:
        deadline=time.monotonic()+10
        while time.monotonic()<deadline and ledger.get(row['id'])['state'] not in ('completed','failed'):
            time.sleep(.1)
        assert ledger.get(row['id'])['state']=='completed'
        assert ledger.get(row['id'])['result']['source']=='MEASURED_MEDIA_METADATA'
    finally:supervisor.stop.set();thread.join(timeout=10)
    assert not thread.is_alive()


def test_shadow_snapshot_stale_and_declared_pose_semantics(tmp_path):
    from engine.demos3d import flying
    from engine.world3d import simulate
    path=tmp_path/'state.json';state={'updated_unix_s':100,'source_connected':True,'stale':False,'prediction':simulate(flying())}
    path.write_text(json.dumps(state))
    live=snapshot(path,now=100.5)
    assert live['fresh'] and len(live['poses'])==3 and live['pose_provenance']=='ASSUMPTION_3D'
    assert not snapshot(path,now=105)['fresh'] and snapshot(path,now=105)['poses']==[]


def test_replay_with_provider_fixture_computes_assumed_prediction(tmp_path,monkeypatch):
    pytest.importorskip('av')
    from integrations.meta import sam
    path=tmp_path/'source.mp4';generate(path);calls=[]
    def segment(*args,**kwargs):
        calls.append(True);x=len(calls)*5
        return {'frames':[{'frame':0,'records':[{'object_id':1,'box':{'x1':x,'x2':x+10,'y1':20,'y2':30,'frame_w':160,'frame_h':120},'confidence':.8}]}],'source':'FIXTURE'}
    monkeypatch.setattr(sam,'segment_image',segment)
    state=run('file',str(path),tmp_path/'state.json',fps=2,sample_s=.5,model=True,frames=4,assumed_scale=.01)
    assert len(calls)>=2 and state['prediction'] is not None
    assert state['prediction']['calibration']['status']=='ASSUMPTION_3D'
    assert not state['physical_actuation']
    # Provider fixture latency is not treated as a live inference benchmark.


def test_reconnect_budget_backoff_and_stale_state_are_software_fixtures(tmp_path,monkeypatch):
    import edge.runtime as runtime
    attempts=[];backoffs=[]
    class Channel(queue.Queue):
        def close(self):pass
    class Process:
        def start(self):attempts.append(True)
        def join(self,timeout=None):pass
        def is_alive(self):return False
    class Context:
        def Queue(self,maxsize):
            channel=Channel(maxsize);channel.put({'error':'fixture_disconnected'});return channel
        def Event(self):return threading.Event()
        def Process(self,**kwargs):return Process()
    monkeypatch.setattr(runtime.multiprocessing,'get_context',lambda kind:Context())
    monkeypatch.setattr(runtime,'_backoff',lambda seconds:backoffs.append(seconds))
    result=runtime.run('usb',0,tmp_path/'state.json')
    assert len(attempts)==4 and backoffs==[1,2,4]
    assert result['reconnect_attempts']==3 and result['stale'] and not result['source_connected']
