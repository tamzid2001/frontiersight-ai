"""Loopback-only video worker API with an operator bearer key and strict origins."""
import argparse
import hmac
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import threading
from urllib.parse import urlsplit,parse_qs
from .video_jobs import Jobs
from .worker import Supervisor


class Handler(BaseHTTPRequestHandler):
    server_version='FrontierSightEdge'
    sys_version=''
    def log_message(self,*args):pass
    def send(self,status,value):
        data=json.dumps(value,allow_nan=False).encode();self.send_response(status)
        origin=self.headers.get('Origin')
        if origin in self.server.origins:self.send_header('Access-Control-Allow-Origin',origin)
        self.send_header('Vary','Origin');self.send_header('Access-Control-Allow-Private-Network','true')
        self.send_header('Content-Type','application/json');self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
    def allowed(self):
        origin=self.headers.get('Origin')
        if origin and origin not in self.server.origins:self.send(403,{'error':'origin_denied'});return False
        token=self.headers.get('Authorization','').removeprefix('Bearer ')
        if not hmac.compare_digest(token,self.server.token):self.send(401,{'error':'edge_operator_token_required'});return False
        return True
    def do_OPTIONS(self):
        if self.headers.get('Origin') not in self.server.origins:return self.send(403,{'error':'origin_denied'})
        self.send_response(204);self.send_header('Access-Control-Allow-Origin',self.headers['Origin'])
        self.send_header('Access-Control-Allow-Methods','GET, POST, OPTIONS');self.send_header('Access-Control-Allow-Headers','Authorization, Content-Type, Upload-Offset')
        self.send_header('Access-Control-Allow-Private-Network','true');self.end_headers()
    def do_GET(self):
        if not self.allowed():return
        path=urlsplit(self.path).path
        if path=='/state':
            try:
                from integrations.ros2_shadow import snapshot
                value=snapshot(self.server.ledger.root/'live-state.json')
                if value.get('state',{}).get('prediction'):
                    prediction=value['state']['prediction'];value['state']['prediction']={k:prediction[k] for k in ('scene','events','source_digest','calibration') if k in prediction}
                return self.send(200,value)
            except (ValueError,OSError):return self.send(200,{'fresh':False,'physical_actuation':False,'poses':[],'risks':[],'error':'runtime_not_connected'})
        if path=='/health':return self.send(200,{'status':'connected','mode':'OFFLINE_REPLAY','physical_actuation':False,'live_camera_connected':False,
            'worker':'process_isolated','retention_seconds':86400,'local_workspace':'single_operator','sam_configured':bool(os.environ.get('MODEL_API_KEY'))})
        if path.startswith('/jobs/'):
            try:return self.send(200,self.server.ledger.get(path.split('/')[-1]))
            except (KeyError,ValueError):return self.send(404,{'error':'job_not_found'})
        self.send(404,{'error':'route_not_found'})
    def do_POST(self):
        if not self.allowed():return
        try:
            path=urlsplit(self.path).path
            length=int(self.headers.get('Content-Length','0'))
            if not 0<=length<=1024*1024:raise ValueError('request_size_limit')
            raw=self.rfile.read(length)
            if path.endswith('/chunk'):
                identity=path.split('/')[2];result=self.server.ledger.append(identity,int(self.headers.get('Upload-Offset','-1')),raw)
            else:
                if self.headers.get('Content-Type','').split(';')[0]!='application/json':raise ValueError('json_content_type_required')
                data=json.loads(raw or b'{}',parse_constant=lambda x:(_ for _ in ()).throw(ValueError('nonfinite_json')))
                if not isinstance(data,dict):raise ValueError('object_required')
                if path=='/mcp':
                    method=data.get('method');name=data.get('params',{}).get('name')
                    if method=='tools/list':result={'tools':[{'name':n,'description':'Read local shadow runtime state; no actuation','inputSchema':{'type':'object','properties':{},'additionalProperties':False}} for n in ('inspect_live_session','get_tracking_diagnostics')]}
                    elif method=='initialize':result={'protocolVersion':'2025-11-25','capabilities':{'tools':{}},'serverInfo':{'name':'frontiersight-edge','version':'0.39.0'}}
                    elif method=='tools/call' and name in ('inspect_live_session','get_tracking_diagnostics'):
                        from integrations.ros2_shadow import snapshot
                        try:value=snapshot(self.server.ledger.root/'live-state.json')
                        except (ValueError,OSError):value={'fresh':False,'physical_actuation':False,'error':'runtime_not_connected'}
                        if name=='get_tracking_diagnostics':value={k:value[k] for k in ('fresh','age_s','physical_actuation','error') if k in value}
                        result={'content':[{'type':'text','text':json.dumps(value)}],'structuredContent':value}
                    else:raise ValueError('unsupported_edge_mcp_method')
                    return self.send(200,{'jsonrpc':'2.0','id':data.get('id'),'result':result})
                if path=='/uploads':result=self.server.ledger.create(data.get('name'),data.get('size'),data.get('concepts'),data.get('mode','inspect'))
                else:
                    pieces=path.split('/')
                    if len(pieces)!=4 or pieces[1]!='jobs':raise ValueError('invalid_job_route')
                    identity,action=pieces[2:]
                    if action=='finish':result=self.server.ledger.finish(identity)
                    elif action=='delete':result=self.server.ledger.delete(identity)
                    else:result=self.server.ledger.control(identity,action)
            self.send(200,result)
        except KeyError:self.send(404,{'error':'job_not_found'})
        except (ValueError,TypeError,OverflowError):self.send(400,{'error':'invalid_job_request_or_transition'})
        except Exception:self.send(503,{'error':'local_video_service_unavailable'})


def serve(root,port=8830,origins=(),host="127.0.0.1"):
    if host!="127.0.0.1" and not (host=="0.0.0.0" and os.environ.get("EDGE_ALLOW_CONTAINER_BIND")=="true"):raise ValueError("non-loopback binding requires explicit container configuration")
    ledger=Jobs(root);keyfile=ledger.root/'operator-token'
    if not keyfile.exists():keyfile.write_text(secrets.token_urlsafe(32));os.chmod(keyfile,0o600)
    token=keyfile.read_text().strip()
    if len(token)<32:raise ValueError('operator_token_too_short')
    # One supervisor owns a ledger; prevent a second server from re-queuing an
    # active worker and duplicating a paid request.
    import fcntl
    lock=(ledger.root/'worker.lock').open('a')
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    server=ThreadingHTTPServer((host,port),Handler);server.timeout=1
    server.token=token;server.origins=set(origins);server.ledger=ledger
    supervisor=Supervisor(ledger);thread=threading.Thread(target=supervisor.run,daemon=True);thread.start()
    print(f'Local edge worker: http://127.0.0.1:{port}; token is in {keyfile} (not printed). Actuation disabled.',flush=True)
    try:server.serve_forever()
    finally:supervisor.stop.set();server.shutdown();server.server_close();thread.join(timeout=10);lock.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',default='~/.local/share/frontiersight-edge');parser.add_argument('--port',type=int,default=8830)
    parser.add_argument('--host',default='127.0.0.1',choices=['127.0.0.1','0.0.0.0']);parser.add_argument('--origin',action='append',default=['https://frontiersight-ai.vercel.app','http://127.0.0.1:8000'])
    args=parser.parse_args();serve(args.root,args.port,args.origin,args.host)
