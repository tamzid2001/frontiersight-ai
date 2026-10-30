"""Bounded camera/file acquisition + sampled SAM inference + shadow state.

No motor, brake, CAN-write or robot-command code exists in this runtime.
Metadata-only replay works without model credentials; no tracks are substituted.
"""
import argparse
import base64
from collections import deque
import hashlib
import json
import math
import multiprocessing
from pathlib import Path
import queue
import time
import os
from urllib.parse import urlsplit
from engine.observations3d import estimate_track,assumption_scene
from engine.world3d import simulate


def source_config(kind,value,allowed_rtsp_hosts=()):
    if kind=='file':
        path=Path(value).expanduser().resolve()
        if not path.is_file():raise ValueError('video_file_not_found')
        return str(path)
    if kind=='usb':
        if not str(value).isdigit() or not 0<=int(value)<=15:raise ValueError('USB camera index must be 0..15')
        return int(value)
    if kind=='rtsp':
        parsed=urlsplit(value)
        if parsed.scheme not in ('rtsp','rtsps') or parsed.hostname not in set(allowed_rtsp_hosts) or parsed.fragment:
            raise ValueError('RTSP requires an explicitly allowed camera hostname; no automatic network discovery')
        return value
    raise ValueError('unsupported_input_adapter')


def _put_latest(output,item):
    try:output.put_nowait(item);return 0
    except queue.Full:
        try:output.get_nowait()
        except queue.Empty:pass
        try:output.put_nowait(item)
        except queue.Full:return 1
        return 1


def acquire(kind,value,output,stop,fps=15):
    """Run in a separate process so hung native capture is terminable."""
    try:
        if kind=='file':
            import av
            with av.open(value,options={'protocol_whitelist':'file'}) as source:
                last=None
                for index,frame in enumerate(source.decode(video=0)):
                    if stop.is_set():break
                    if frame.pts is None:raise ValueError('source_pts_unavailable')
                    pts=float(frame.pts*frame.time_base)
                    if last is not None and pts<=last:raise ValueError('source_pts_nonmonotonic')
                    last=pts
                    if frame.width*frame.height>3840*2160:raise ValueError('frame_resolution_limit')
                    image=frame.to_image();image.thumbnail((960,540));import io
                    buffer=io.BytesIO();image.save(buffer,format='JPEG',quality=75)
                    _put_latest(output,{'index':index,'source_pts_s':pts,'captured_monotonic_s':time.monotonic(),
                        'width':image.width,'height':image.height,'jpeg':buffer.getvalue(),'source_timestamp_kind':'media_pts'})
                    if stop.wait(1/fps):break
        else:
            import cv2
            capture=cv2.VideoCapture()
            params=[cv2.CAP_PROP_OPEN_TIMEOUT_MSEC,3000,cv2.CAP_PROP_READ_TIMEOUT_MSEC,3000] if kind=='rtsp' else []
            try:
                opened=capture.open(value,cv2.CAP_FFMPEG,params) if kind=='rtsp' else capture.open(value)
                if not opened:raise ValueError('camera_open_failed')
                index=0
                while not stop.is_set():
                    ok,image=capture.read();stamp=time.monotonic()
                    if not ok:raise ValueError('camera_disconnected')
                    h,w=image.shape[:2]
                    if w*h>3840*2160:raise ValueError('camera_resolution_limit')
                    scale=min(1,960/w,540/h)
                    if scale<1:image=cv2.resize(image,(round(w*scale),round(h*scale)))
                    ok,jpeg=cv2.imencode('.jpg',image,[cv2.IMWRITE_JPEG_QUALITY,75])
                    if not ok:raise ValueError('camera_frame_encode_failed')
                    _put_latest(output,{'index':index,'source_pts_s':stamp,'captured_monotonic_s':stamp,
                        'width':image.shape[1],'height':image.shape[0],'jpeg':jpeg.tobytes(),'source_timestamp_kind':'host_capture_monotonic_not_sensor_hardware_timestamp'})
                    index+=1
                    if stop.wait(1/fps):break
            finally:capture.release()
        _put_latest(output,{'end':True})
    except Exception:
        _put_latest(output,{'error':'source_disconnected_or_decode_failed'})


def percentile(values,q):
    if not values:return None
    data=sorted(values);index=(len(data)-1)*q;lo=int(index);hi=min(lo+1,len(data)-1)
    return data[lo]+(data[hi]-data[lo])*(index-lo)


def write_state(path,state):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    temporary=path.with_suffix('.new');temporary.write_text(json.dumps(state,allow_nan=False));os.chmod(temporary,0o600);os.replace(temporary,path)


class Tracker:
    """Bounded nearest-centre association; provisional identity, never SAM video IDs."""
    def __init__(self):self.tracks={};self.serial=0
    def update(self,parsed,t):
        candidates=[r for f in parsed.get('frames',[]) for r in f['records']][:32]
        used=set();updated=[]
        for record in candidates:
            b=record['box'];point=[(b['x1']+b['x2'])/2,(b['y1']+b['y2'])/2]
            possible=[]
            for identity,rows in self.tracks.items():
                if identity in used or not 0<t-rows[-1]['t_s']<=2:continue
                distance=math.dist(point,rows[-1]['position'])
                if distance<=max(30,.5*math.hypot(b['x2']-b['x1'],b['y2']-b['y1'])):possible.append((distance,identity))
            identity=min(possible)[1] if possible else 'provisional-'+str(self.serial)
            if not possible:self.serial+=1
            rows=self.tracks.setdefault(identity,[])
            rows.append({'t_s':t,'position':point,'confidence':record.get('confidence')});del rows[:-20]
            used.add(identity);updated.append({'object_id':identity,'points':list(rows),'identity_status':'ASSUMPTION_NEAREST_CENTER',
                'kinematics':estimate_track(rows,max_gap_s=2) if len(rows)>=2 else None})
        self.tracks={k:v for k,v in self.tracks.items() if t-v[-1]['t_s']<=2 and k in used}
        return updated


def run(kind,value,output_path,*,fps=15,sample_s=2.,model=False,concept='person',frames=0,assumed_scale=None):
    if not 1<=fps<=30 or not .5<=sample_s<=60:raise ValueError('capture/sample rate out of range')
    ctx=multiprocessing.get_context('spawn');channel=ctx.Queue(maxsize=2);stop=ctx.Event()
    process=ctx.Process(target=acquire,args=(kind,value,channel,stop,fps));process.start()
    tracker=Tracker();latencies=deque(maxlen=1000);inference=deque(maxlen=1000);count=0;last_index=-1;dropped=0;last_sample=-math.inf;tracks=[]
    last_observation_capture=None
    state={'schema_version':'2.0','mode':'OFFLINE_REPLAY' if kind=='file' else 'SHADOW','physical_actuation':False,
           'source_connected':False,'source_type':kind,'tracks':[],'prediction':None,'timestamp_kind':'none'}
    try:
        while True:
            try:frame=channel.get(timeout=5)
            except queue.Empty:
                state.update(source_connected=False,stale=True,error='source_timeout',updated_unix_s=time.time());write_state(output_path,state)
                if not process.is_alive():break
                continue
            if frame.get('end') or frame.get('error'):
                state.update(source_connected=False,stale=True,error=frame.get('error','replay_completed'),updated_unix_s=time.time());write_state(output_path,state);break
            now=time.monotonic();age=now-frame['captured_monotonic_s'];latencies.append(age*1000)
            dropped+=max(0,frame['index']-last_index-1);last_index=frame['index'];count+=1
            t=frame['source_pts_s'];inference_age=None
            if model and now-last_sample>=sample_s:
                from integrations.meta.sam import segment_image
                started=time.monotonic()
                parsed=segment_image('data:image/jpeg;base64,'+base64.b64encode(frame['jpeg']).decode(),concept,timeout=20)
                inference.append((time.monotonic()-started)*1000);tracks=tracker.update(parsed,t);last_sample=now;last_observation_capture=frame['captured_monotonic_s']
            prediction=None
            prediction_age=time.monotonic()-last_observation_capture if last_observation_capture is not None else None
            if tracks and assumed_scale is not None and prediction_age is not None and prediction_age<=2:
                valid=[r for r in tracks if len(r['points'])>=2]
                if valid:
                    prediction=simulate(assumption_scene(valid[:16],assumed_scale))
            state.update(source_connected=True,stale=time.monotonic()-frame['captured_monotonic_s']>2,updated_unix_s=time.time(),sequence=frame['index'],
                source_pts_s=t,timestamp_kind=frame['source_timestamp_kind'],tracks=tracks,prediction=prediction,
                calibration_status='ASSUMPTION_3D' if prediction else 'PIXEL_ONLY_2D',perception_status='MODEL_DERIVED' if model else 'NOT_RUN',
                metrics={'processed_frames':count,'frames_dropped':dropped,'capture_to_consumer_ms':age*1000,
                         'capture_latency_ms':{str(q):percentile(latencies,q) for q in (.5,.95,.99)},
                         'inference_latency_ms':{str(q):percentile(inference,q) for q in (.5,.95,.99)},'prediction_age_s':prediction_age,'perception_stale':prediction_age is None or prediction_age>2},
                inference_note='Independent image calls; provisional association can switch identities. No camera ego-motion compensation.')
            write_state(output_path,state)
            if frames and count>=frames:break
    except KeyboardInterrupt:pass
    finally:
        stop.set();process.join(timeout=3)
        if process.is_alive():process.terminate();process.join(timeout=3)
        state.update(source_connected=False,stale=True,updated_unix_s=time.time());write_state(output_path,state)
        channel.close()
    return state


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--source',choices=['file','usb','rtsp'],required=True);parser.add_argument('--input',required=True)
    parser.add_argument('--allow-rtsp-host',action='append',default=[]);parser.add_argument('--output',default='~/.local/share/frontiersight-edge/live-state.json')
    parser.add_argument('--fps',type=int,default=15);parser.add_argument('--sample-seconds',type=float,default=2);parser.add_argument('--sam',action='store_true')
    parser.add_argument('--concept',default='person');parser.add_argument('--max-frames',type=int,default=0);parser.add_argument('--assumed-metres-per-pixel',type=float)
    args=parser.parse_args();run(args.source,source_config(args.source,args.input,args.allow_rtsp_host),Path(args.output).expanduser(),fps=args.fps,sample_s=args.sample_seconds,model=args.sam,concept=args.concept,frames=args.max_frames,assumed_scale=args.assumed_metres_per_pixel)
