import json
import pytest
from integrations.meta import sam
from integrations.meta.credentials import using_key
from integrations.meta.spark import ModelError


class Stream:
    status=200
    def __init__(self,events):self.lines=iter(('data:'+json.dumps(e)+'\n').encode() for e in events)
    def __enter__(self):return self
    def __exit__(self,*a):pass
    def readline(self,*a):return next(self.lines,b'')


def test_video_requires_completed_stream_and_bound_reference(monkeypatch):
    events=[{'type':'response.output_text.delta','delta':'<0f>1<|box;x1=0;y1=0;x2=5;y2=5;w=10;h=10;c=0.8|>'},{'type':'response.completed'}]
    monkeypatch.setattr(sam.urllib.request,'urlopen',lambda *a,**k:Stream(events))
    with using_key('fixture-model-key'):
        result=sam.segment_video('file-fixture','person',is_file_id=True,timeout=1)
        assert result['objects']==[1] and result['source']=='MODEL_DERIVED'
        events.pop()
        with pytest.raises(ModelError):sam.segment_video('file-fixture','person',is_file_id=True)
        for ref,file_id in [('https://127.0.0.1/video',False),('file-fixture\nheader',True)]:
            with pytest.raises(ValueError):sam.segment_video(ref,'person',is_file_id=file_id)
        with pytest.raises(ValueError):sam.segment_video('file-fixture','person,car',is_file_id=True)
        events[:]=[{'type':'response.completed'}]
        assert sam.segment_video('file-fixture','person',is_file_id=True)['objects']==[]
        events[:]=[{'type':'response.incomplete'}]
        with pytest.raises(ModelError):sam.segment_video('file-fixture','person',is_file_id=True)


def test_files_api_envelope_and_safe_errors(tmp_path,monkeypatch):
    import io
    import urllib.error
    from integrations.meta import video_upload
    from integrations.meta.spark import BlockedCredentials
    path=tmp_path/'clip.media';path.write_bytes(b'fixture media bytes, not a real upload')
    calls=[]
    class Response(io.BytesIO):status=200
    def opened(request,**kw):
        calls.append(request)
        return Response(b'{"id":"file-fixture"}')
    monkeypatch.setattr(video_upload.urllib.request,'urlopen',opened)
    with using_key('fixture-not-a-real-key'):
        assert video_upload.upload_video(path,'name.mov')=='file-fixture'
        assert b'name="purpose"' in calls[0].data and b'user_data' in calls[0].data and b'video/quicktime' in calls[0].data
        assert video_upload.delete_upload('file-fixture')
        with pytest.raises(ValueError):video_upload.upload_video(path,'bad.exe')
        with pytest.raises(ValueError):video_upload.delete_upload('../credential')
        def failure(*args,**kw):raise urllib.error.HTTPError('fixture',403,'forbidden',{},None)
        monkeypatch.setattr(video_upload.urllib.request,'urlopen',failure)
        with pytest.raises(ModelError):video_upload.upload_video(path,'video.mp4')
        assert video_upload.delete_upload('file-fixture') is False
    monkeypatch.delenv('MODEL_API_KEY',raising=False)
    with pytest.raises(BlockedCredentials):video_upload.upload_video(path,'video.mp4')
