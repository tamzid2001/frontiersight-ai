"""Bounded local Files API transfer, following Meta's user_data upload contract."""
from pathlib import Path
import json
import re
import urllib.request
import urllib.error
import uuid
from .credentials import api_key
from .spark import BASE,BlockedCredentials,ModelError


def upload_video(path,filename="video.mp4"):
    key=api_key()
    if not key: raise BlockedCredentials('Meta key unavailable; no video was transmitted')
    path=Path(path)
    if not path.is_file() or not 0<path.stat().st_size<=64*1024*1024: raise ValueError('video_size_limit')
    suffix=Path(filename).suffix.lower()
    if suffix not in ('.mp4','.mov','.webm'):raise ValueError('unsupported video extension')
    boundary='frontiersight-'+uuid.uuid4().hex
    mime={'.webm':'video/webm','.mov':'video/quicktime'}.get(suffix,'video/mp4')
    data=(f'--{boundary}\r\nContent-Disposition: form-data; name="purpose"\r\n\r\nuser_data\r\n'
          f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="video{suffix}"\r\nContent-Type: {mime}\r\n\r\n').encode()+path.read_bytes()+f'\r\n--{boundary}--\r\n'.encode()
    request=urllib.request.Request(BASE+'/files',data=data,method='POST',headers={'Authorization':'Bearer '+key,'Content-Type':'multipart/form-data; boundary='+boundary})
    try:
        with urllib.request.urlopen(request,timeout=30) as response:
            raw=response.read(65537)
            if len(raw)>65536: raise ModelError('Files API response exceeded bound')
            result=json.loads(raw)
    except urllib.error.HTTPError as error: raise ModelError(f'Video upload HTTP {error.code}; no automatic retry') from None
    identity=result.get('id','')
    if not isinstance(identity,str) or not re.fullmatch(r'file-[A-Za-z0-9_-]{1,160}',identity): raise ModelError('Invalid Files API identifier')
    return identity


def delete_upload(identity):
    if not re.fullmatch(r'file-[A-Za-z0-9_-]{1,160}',identity): raise ValueError('invalid uploaded file')
    request=urllib.request.Request(BASE+'/files/'+identity,method='DELETE',headers={'Authorization':'Bearer '+api_key()})
    try:
        with urllib.request.urlopen(request,timeout=10) as response:return response.status in (200,204)
    except (OSError,urllib.error.URLError):return False
