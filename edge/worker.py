"""Killable local decoding/model worker. One process/job, no silent model retry."""
import multiprocessing
import threading
import time
from .video_jobs import Jobs
from .media import inspect_video


def process_job(root,identity):
    ledger=Jobs(root);job=ledger.get(identity);uploaded=None
    try:
        def checkpoint(*args):
            if ledger.get(identity)['state']!='running': raise InterruptedError('job_not_running')
        metadata=job['metadata'] or inspect_video(ledger.path(identity),checkpoint)
        ledger.update(identity,metadata=metadata)
        checkpoint()
        if job['mode']=='inspect':
            ledger.update(identity,state='completed',result={'metadata':metadata,'tracks':[],'perception_status':'NOT_RUN','source':'MEASURED_MEDIA_METADATA'})
            return
        if metadata['frame_count']>512: raise ValueError('sam_video_frame_limit_512; use a shorter clip')
        from integrations.meta.credentials import api_key
        if not api_key(): raise ValueError('model_credentials_unavailable; inspection_complete; no synthetic tracks substituted')
        ledger.update(identity,model_started=1)
        from integrations.meta.video_upload import upload_video,delete_upload
        from integrations.meta.sam import segment_video
        from engine.observations3d import sam_tracks
        uploaded=upload_video(ledger.path(identity),job['name'])
        results=[]
        for index,concept in enumerate(job['concepts']):
            checkpoint();parsed=segment_video(uploaded,concept,is_file_id=True,timeout=45)
            if any(d.get('code') in ('frame_limit','frame_record_limit') for d in parsed.get('diagnostics',[])): raise ValueError('model_output_truncated')
            result=sam_tracks(parsed,metadata['frame_timestamps_s'])
            for track in result['tracks']:track['object_id']=f'c{index}-'+track['object_id'];track['concept']=concept
            results.append({'concept':concept,'segmentation':parsed,'tracking':result})
        ledger.update(identity,state='completed',result={'metadata':metadata,'concepts':results,'tracks':[t for r in results for t in r['tracking']['tracks']],
            'source':'MODEL_DERIVED','calibration_status':'PIXEL_ONLY_2D','depth_available':False})
    except Exception as error:
        current=ledger.get(identity)
        # Store stable codes, never upstream response bodies, credentials or paths.
        code=str(error) if isinstance(error,(ValueError,InterruptedError)) else 'video_worker_failed'
        ledger.update(identity,state='failed_or_unknown' if current['model_started'] else 'failed',error=code[:200])
    finally:
        if uploaded:
            from integrations.meta.video_upload import delete_upload
            delete_upload(uploaded)


class Supervisor:
    def __init__(self,ledger):self.ledger=ledger;self.stop=threading.Event();self.active=None
    def run(self):
        self.ledger.recover()
        try:
            while not self.stop.wait(.2):
                if self.active:
                    identity,process,started=self.active
                    current=self.ledger.get(identity)
                    if current['state']!='running' or time.monotonic()-started>360:
                        if process.is_alive():process.terminate()
                    if not process.is_alive():
                        process.join()
                        if current['state']=='running':self.ledger.update(identity,state='failed_or_unknown' if current['model_started'] else 'failed',error='worker_exit_or_timeout')
                        self.active=None
                else:
                    self.ledger.expire();identity=self.ledger.claim()
                    if identity:
                        process=multiprocessing.get_context('spawn').Process(target=process_job,args=(str(self.ledger.root),identity))
                        process.start();self.active=(identity,process,time.monotonic())
        finally:
            if self.active:
                identity,process,_=self.active
                if process.is_alive():process.terminate()
                process.join(timeout=5)
                current=self.ledger.get(identity)
                self.ledger.update(identity,state='failed_or_unknown' if current['model_started'] else 'paused',error='operator_shutdown')
