"""Small Python REST client. No automatic retries, no credentials in URLs/logs."""
from __future__ import annotations
import json
import os
import re
from urllib.parse import urlparse
import urllib.request
import urllib.error
import uuid


class APIError(RuntimeError):
    def __init__(self,status,code):
        super().__init__(f'FrontierSight HTTP {status}: {code}')
        self.status,self.code=status,code


class FrontierSight:
    def __init__(self, token=None, *, base_url='https://frontiersight-ai.vercel.app', timeout=40, organization=None):
        parsed=urlparse(base_url)
        if parsed.scheme not in ('https','http') or not parsed.hostname or parsed.path or parsed.query or parsed.fragment or parsed.username or parsed.password:
            raise ValueError('base_url must be an origin')
        if parsed.scheme!='https' and parsed.hostname not in ('127.0.0.1','localhost'):
            raise ValueError('HTTPS is required outside localhost')
        if isinstance(timeout,bool) or not isinstance(timeout,(int,float)) or not 1<=timeout<=60:
            raise ValueError('timeout must be 1..60 seconds')
        self.base_url,self.timeout,self.organization=base_url.rstrip('/'),timeout,organization
        self.last_request_key=None
        self.token=token if token is not None else os.environ.get('FRONTIERSIGHT_API_KEY','')

    def call(self, path, body, *, request_key=None, api_version="v1"):
        if api_version not in ("v1","v2"):raise ValueError("unsupported API version")
        if not isinstance(path,str) or not re.fullmatch(r'[a-z-]+/[a-z-]+',path):
            raise ValueError('path must be resource/operation, without URL or query')
        token=self.token() if callable(self.token) else self.token
        if not isinstance(token,str) or (not token and api_version=='v1') or any(ch.isspace() for ch in token):
            raise ValueError('a Bearer token/key is required')
        self.last_request_key=request_key or str(uuid.uuid4())
        headers={'Content-Type':'application/json',
                 'Idempotency-Key':self.last_request_key}
        if token:headers['Authorization']='Bearer '+token
        if self.organization is not None:headers['X-Workspace-Organization']=self.organization
        request=urllib.request.Request(self.base_url+'/api/'+api_version+'/'+path,data=json.dumps(body,allow_nan=False).encode(),headers=headers)
        try:
            with urllib.request.urlopen(request,timeout=self.timeout) as response:
                return json.loads(response.read(4_500_000))
        except urllib.error.HTTPError as error:
            try: code=json.loads(error.read(10000)).get('error','request_failed')
            except (ValueError,AttributeError):code='request_failed'
            raise APIError(error.code,str(code)[:200]) from None

    def create_scene(self,name,scene,**options):return self.call('scenes/create',{'name':name,'scene':scene},**options)
    def get_scene(self,record_id):return self.call('scenes/get',{'id':record_id})['record']
    def plan_path(self,scene,object_id,goal,**settings):return self.call('paths/plan',{'scene':scene,'object_id':object_id,'goal':goal,**settings})
    def predict_path(self,points,**settings):return self.call('paths/predict',{'points':points,**settings})
    def generate_scene(self,description,*,candidates=3,request_key=None):return self.call('scenes/generate',{'description':description,'candidates':candidates},request_key=request_key)
    def describe_paths(self,scene,description,*,request_key=None):return self.call('paths/describe',{'scene':scene,'description':description},request_key=request_key)
    def save_object(self,name,spec,**options):return self.call('objects/create',{'name':name,'spec':spec},**options)
    def use_object(self,scene,object_record_id,object_id,x,y):return self.call('objects/use',{'scene':scene,'object_record_id':object_record_id,'object_id':object_id,'x':x,'y':y})
    def render_frame(self,scene,**settings):return self.call('media/render-frame',{'scene':scene,**settings})
    def render_preview(self,scene,**settings):return self.call('media/render-preview',{'scene':scene,**settings})
    def model_receipt(self,request_key):return self.call('model-requests/get',{'request_key':request_key})
