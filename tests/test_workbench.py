"""Real engine + local Firestore + HTTP/MCP; provider invocations use fixtures."""
import base64
import copy
import io
import json
import os
import threading
import uuid
import urllib.request
import urllib.error
from http.server import ThreadingHTTPServer

import pytest
from PIL import Image
from services.api.clerk_auth import Identity, WorkspaceError
from services.api.firestore_scenes import Scenes, client
from services.api.workbench import Workbench, decode_frame, media_payload, use_object
from integrations.meta import spark
from integrations.meta.path_edit import apply_path_edits, describe_paths
from engine.scene_media import render_frame, render_video_preview


def scene():
    return {'stage_metres':[16,14],'objects':[
        {'id':'robot-7','category':'robot','waypoints':[[2,3],[12,3]],'radius':.5,'speed':1,'delay':0,'mode':'stop','curve':'straight'},
        {'id':'shelf-4','category':'shelf','waypoints':[[8,8]],'radius':1,'speed':0}]}


def png():
    stream=io.BytesIO();Image.new('RGB',(12,10),'red').save(stream,format='PNG')
    return 'data:image/png;base64,'+base64.b64encode(stream.getvalue()).decode()


@pytest.fixture
def service():
    if not os.environ.get('FIRESTORE_EMULATOR_HOST'):pytest.skip('Local Firestore emulator required')
    db=client({'FIRESTORE_PROJECT_ID':'demo-quantura-web','FIRESTORE_EMULATOR_HOST':os.environ['FIRESTORE_EMULATOR_HOST']})
    identity=Identity('user_'+uuid.uuid4().hex,None,None,'researcher')
    stores={kind:Scenes(db,identity,'test-audit-secret-'*3,resource=kind) for kind in ('scenes','objects','media')}
    yield Workbench(identity,stores=stores)
    db.close()


def test_versioned_scene_crud_roundtrip_replay_and_cross_tenant_isolation(service):
    data={'name':'Warehouse','scene':scene()};snapshot=copy.deepcopy(data)
    created=service.execute('create_scenes',data,'scene-create-idempotency')
    assert service.execute('create_scenes',data,'scene-create-idempotency')['replayed']
    row=service.execute('get_scenes',{'id':created['id']})['record']
    assert row['payload']==scene() and data==snapshot
    assert service.execute('list_scenes',{})['items'][0]['id']==created['id']
    update={**data,'id':created['id'],'expectedVersion':1}
    service.execute('update_scenes',update,'scene-update-idempotency')
    with pytest.raises(WorkspaceError):service.execute('update_scenes',update,'scene-stale-idempotency')
    with pytest.raises(WorkspaceError):service.execute('create_scenes',{'name':'Different','scene':scene()},'scene-create-idempotency')
    another=Scenes(service.store('scenes').db,Identity('user_other',None,None,'explorer'),'secret-'*8)
    with pytest.raises(WorkspaceError):another.get(created['id'])
    service.execute('delete_scenes',{'id':created['id'],'expectedVersion':2},'scene-delete-idempotency')
    with pytest.raises(WorkspaceError):service.execute('get_scenes',{'id':created['id']})


def test_saved_object_reuse_keeps_dimensions_ids_and_spec(service):
    spec=spark.procedural_object('warehouse robot')
    saved=service.execute('create_objects',{'name':'My robot','spec':spec},'object-create-idempotency')
    result=service.execute('use_object',{'object_record_id':saved['id'],'scene':scene(),'object_id':'custom-21','x':4,'y':10})
    document=result['scene'];assert document['stage_metres']==[16,14]
    assert document['objects'][-1]['id']=='custom-21' and document['objects'][-1]['custom']['spec']==spec
    assert len(document['objects'])==3 and len(scene()['objects'])==2
    with pytest.raises(ValueError):service.execute('use_object',{'object_record_id':saved['id'],'scene':scene(),'object_id':'robot-7','x':4,'y':10})
    with pytest.raises(ValueError):use_object(scene(),spec,'new',0,0)


def test_saved_video_frame_parent_relationship_and_segmentation_receipts(service,monkeypatch):
    video=service.execute('create_media',{'name':'Source','kind':'video','provider_file_id':'file_source123'},'video-create-idempotency')
    frame=service.execute('create_media',{'name':'Frame','kind':'frame','data_url':png(),'timestamp_s':2,'source_video_id':video['id']},'frame-create-idempotency')
    calls=[]
    monkeypatch.setattr(spark,'configured',lambda:True)
    monkeypatch.setattr('services.api.workbench.sam.segment_image',lambda *a,**kw:calls.append((a,kw)) or {'frames':[],'source':'MODEL_DERIVED'})
    body={'media_id':frame['id'],'concept':'robot'}
    first=service.execute('segment_frame',body,'segment-frame-idempotency')
    assert first['replayed'] is False
    assert service.execute('segment_frame',body,'segment-frame-idempotency')['replayed'] is True
    assert len(calls)==1 and calls[0][1]['timeout']==25
    status=service.execute('get_model_request',{'request_key':'segment-frame-idempotency'})
    assert status['status']=='completed'
    with pytest.raises(ValueError):service.execute('create_media',{'name':'bad parent','kind':'frame','data_url':png(),'source_video_id':frame['id']},'frame-badparent-idempotency')
    monkeypatch.setattr('services.api.workbench.sam.segment_video',lambda *a,**kw:{'file':a[0],'file_id':kw['is_file_id']})
    with pytest.raises(WorkspaceError) as denied:
        service.execute('segment_video',{'media_id':video['id']},'host-video-access-denied')
    assert denied.value.status==403
    from services.api.workbench import provider_key
    monkeypatch.setenv('BYOK_ENCRYPTION_KEY','test-video-encryption-secret')
    provider_key(service.store('scenes'),service.identity,'save','LLM_fixture_video_account_key_123')
    assert service.execute('segment_video',{'media_id':video['id']},'segment-video-idempotency')['file_id']


def test_failed_provider_attempt_is_never_replayed(service,monkeypatch):
    count=[]
    def failure(*args):count.append(1);raise RuntimeError('private upstream detail')
    monkeypatch.setattr(spark,'design_custom_object',failure)
    body={'description':'robot'}
    with pytest.raises(RuntimeError):service.execute('generate_object',body,'failure-request-idempotency')
    with pytest.raises(WorkspaceError):service.execute('generate_object',body,'failure-request-idempotency')
    assert count==[1]
    assert service.execute('get_model_request',{'request_key':'failure-request-idempotency'})['status']=='failed_or_unknown'
    with pytest.raises(WorkspaceError):service.execute('get_model_request',{'request_key':'unknown-request-idempotency'})


def test_model_tools_require_plan_key_and_single_selection(service,monkeypatch):
    free=Workbench(Identity('user_free',None,None,'explorer'),stores=service._stores)
    with pytest.raises(WorkspaceError) as exc:free.model_call('x',{},'valid-idempotency-key',lambda:{})
    assert exc.value.status==402
    with pytest.raises(WorkspaceError):service.model_call('x',{},'',lambda:{})
    calls=[]
    def generate(*args):calls.append(args);return scene(),{'candidates_requested':args[2]}
    monkeypatch.setattr(spark,'generate_scene',generate)
    result=service.execute('generate_scene',{'description':'warehouse','candidates':8},'generation-request-idempotency')
    assert result['scene']['objects'][0]['id']=='robot-1' and calls[0][2]==8
    with pytest.raises(WorkspaceError):service.execute('generate_scene',{'description':'other','candidates':8},'generation-request-idempotency')


def test_language_edit_is_one_call_preserves_unselected_objects_and_rejects_bad_paths(monkeypatch):
    original=scene();before=copy.deepcopy(original);calls=[]
    edit={'object_id':'robot-7','waypoints':[[2,3],[3,4],[4,5]],'curve':'smooth','speed':1.5}
    def respond(*args,**kwargs):calls.append(kwargs);return json.dumps({'edits':[edit]}),{'model':'fixture'}
    monkeypatch.setattr(spark,'_call',respond)
    result=describe_paths(original,'robot-7 moves diagonally','muse-spark-1.3')
    assert calls==[{'timeout':20,'retries':0,'model':'muse-spark-1.3'}]
    assert result['scene']['objects'][1]==original['objects'][1] and original==before
    assert result['scene']['objects'][0]['path_source']=='MODEL_DERIVED_PLAN'
    for edits in [[],[edit,edit],[{**edit,'object_id':'other'}],[{**edit,'name':'rename'}],[{'object_id':'robot-7'}],[{**edit,'waypoints':[]}],[{**edit,'waypoints':[[0,0],[99,99]]}]]:
        with pytest.raises(ValueError):apply_path_edits(original,edits)
    monkeypatch.setattr(spark,'_call',lambda *a,**kw:('not json',{}))
    with pytest.raises(spark.ModelError):describe_paths(original,'go to the left')
    with pytest.raises(ValueError):describe_paths(original,'')


@pytest.mark.parametrize('bad',[None,'data:text/plain;base64,SGk=','data:image/png;base64,!', 'data:image/png;base64,SGk=', 'data:image/png;base64,'+'A'*180000])
def test_invalid_frames_rejected(bad):
    with pytest.raises(ValueError):decode_frame(bad)


def test_frame_and_video_preview_are_real_decodable_media_and_share_motion():
    result=render_frame(scene(),1,320,240)
    image=Image.open(io.BytesIO(base64.b64decode(result['data_url'].split(',')[1])))
    assert image.size==(320,240) and image.format=='PNG'
    assert result['objects'][0]['object_id']=='robot-7'
    assert result['objects'][0]['position_metres'][0]>2
    preview=render_video_preview(scene(),duration_s=1,fps=6,width=320,height=240)
    image=Image.open(io.BytesIO(base64.b64decode(preview['data_url'].split(',')[1])))
    assert image.format=='GIF' and image.n_frames==6
    assert preview['duration_s']==pytest.approx(1.02) and preview['source']=='SIMULATED_2D_ANIMATED_PREVIEW'
    for args in [{'fps':True},{'fps':20},{'duration_s':12,'fps':15},{'width':2},{'duration_s':.2,'fps':1}]:
        with pytest.raises(ValueError):render_video_preview(scene(),**args)
    for value in [True,-1,float('nan'),21]:
        with pytest.raises(ValueError):render_frame(scene(),value)


def test_published_schemas_reject_unexpected_fields_and_boolean_counts(service):
    for operation,body in [('list_scenes',{'limit':True}),('list_scenes',{'oops':1}),('create_scenes',{'name':'x'}),('predict_path',{'points':[]}),('made_up',{})]:
        with pytest.raises(ValueError):service.execute(operation,body)
    with pytest.raises(WorkspaceError):Workbench(None)
    with pytest.raises(ValueError):media_payload({'kind':'video','provider_file_id':'https://127.0.0.1'})
    with pytest.raises(ValueError):media_payload({'kind':'audio'})


def test_http_and_mcp_use_same_operations_auth_origin_and_versions(service,monkeypatch):
    from services.api.server import H
    from services.api import workbench_http, workbench
    monkeypatch.setattr(workbench_http,'actor',lambda header:service.identity if header=='Bearer verified-fixture' else (_ for _ in ()).throw(WorkspaceError(401,'authentication_required')))
    monkeypatch.setattr(workbench,'actor',workbench_http.actor)
    monkeypatch.setattr(Workbench,'store',lambda self,kind:service._stores[kind])
    monkeypatch.setenv('CLERK_AUTHORIZED_PARTIES','https://frontiersight.example')
    server=ThreadingHTTPServer(('127.0.0.1',0),H);threading.Thread(target=server.serve_forever,daemon=True).start()
    base='http://127.0.0.1:'+str(server.server_port)
    def request(path,data=None,headers=None):
        req=urllib.request.Request(base+path,data=json.dumps(data).encode() if data is not None else None,headers={'Content-Type':'application/json',**(headers or {})})
        try:
            with urllib.request.urlopen(req,timeout=10) as reply:return reply.status,json.load(reply)
        except urllib.error.HTTPError as error:return error.code,json.load(error)
    try:
        headers={'Authorization':'Bearer verified-fixture','Idempotency-Key':'http-scene-request-key'}
        status,saved=request('/api/v1/scenes/create',{'name':'HTTP scene','scene':scene()},headers)
        assert status==200,saved
        rpc={'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':'get_scenes','arguments':{'id':saved['id']}}}
        status,reply=request('/api/mcp',rpc,headers)
        assert reply['result']['structuredContent']['record']['payload']==scene()
        assert request('/api/v1/scenes/list',{})[0]==401
        assert request('/api/v1/scenes/list',{},headers|{'Origin':'https://evil.example'})[0]==403
        assert request('/api/v1/account',None,headers)[1]['userId']==service.identity.user_id
        assert request('/api/mcp',rpc,headers|{'MCP-Protocol-Version':'invalid'})[0]==400
        assert request('/api/mcp',rpc,{'Origin':'https://evil.example'})[0]==403
        assert request('/api/mcp',None,{'Accept':'text/event-stream'})[0]==405
        assert request('/api/v1/no-such',{},headers)[0]==404
        rpc['params']['name']='render_scene_frame';rpc['params']['arguments']={'scene':scene(),'width':320,'height':240}
        assert request('/api/mcp',rpc,headers)[1]['result']['structuredContent']['mime_type']=='image/png'
        assert request('/api/paths/predict',{'points':[[0,1,1],[1,2,1],[2,3,1]]})[1]['source']=='PREDICTED'
        assert request('/api/index?ep=path&operation=plan',{'scene':scene(),'object_id':'robot-7','goal':[12,3]})[0]==200
        assert request('/api/index?ep=v1&resource=scenes/list',{},headers)[0]==200
        from sdk.frontiersight import FrontierSight, APIError
        client=FrontierSight('verified-fixture',base_url=base)
        planned=client.plan_path(scene(),'robot-7',[12,4])
        saved_sdk=client.create_scene('SDK warehouse',planned['scene'])
        recovery_key=client.last_request_key
        assert client.create_scene('SDK warehouse',planned['scene'],request_key=recovery_key)['replayed'] is True
        assert client.get_scene(saved_sdk['id'])['payload']==planned['scene']
        assert client.render_frame(planned['scene'],timestamp_s=2)['mime_type']=='image/png'
        assert client.render_preview(planned['scene'],duration_s=1,width=160,height=120)['mime_type']=='image/gif'
        assert client.predict_path([[0,1,1],[1,2,1],[2,3,1]])['velocity']==[1,0]
        owned=client.save_object('SDK object',spark.procedural_object('robot'))
        assert client.use_object(scene(),owned['id'],'new-sdk-object',4,9)['scene']['objects'][-1]['id']=='new-sdk-object'
        with pytest.raises(APIError):client.model_receipt('unknown-sdk-request-key')
        for path in ['https://evil.example/','../scene','scenes/get?key=secret']:
            with pytest.raises(ValueError):client.call(path,{})
        for url in ['http://evil.example','https://host.example/path','https://user:pass@host.example']:
            with pytest.raises(ValueError):FrontierSight('key',base_url=url)
        with pytest.raises(ValueError):FrontierSight('',base_url=base).call('scenes/list',{})
    finally:server.shutdown();server.server_close()


def test_agent_keys_are_hashed_scoped_expiring_and_revocable(service,monkeypatch):
    from services.api import access_keys
    db=service.store('scenes').db
    grant=access_keys.create(db,service.identity,'Reader',['read'],1)
    assert len(grant['key'])==58
    stored=access_keys.collection(db).document(grant['id']).get().to_dict()
    assert grant['key'] not in json.dumps(stored,default=str)
    identity=access_keys.verify(db,'Bearer '+grant['key'])
    restricted=Workbench(identity,stores=service._stores)
    assert restricted.execute('list_scenes',{})['items']==[]
    with pytest.raises(WorkspaceError) as denied:restricted.execute('create_scenes',{'name':'x','scene':scene()},'scope-test-idempotency')
    assert denied.value.status==403
    assert access_keys.manage(db,service.identity)['keys'][0]['prefix']==grant['prefix']
    with pytest.raises(WorkspaceError):access_keys.manage(db,identity)
    access_keys.manage(db,service.identity,grant['id'])
    with pytest.raises(WorkspaceError):access_keys.verify(db,'Bearer '+grant['key'])
    for scopes,days in [([],1),(['admin'],1),(['read','read'],1),(['read'],0),(['read'],True)]:
        with pytest.raises(ValueError):access_keys.create(db,service.identity,'key',scopes,days)
    for value in ['Bearer other','Bearer fsa_'+('A'*54),'']:
        with pytest.raises(WorkspaceError):access_keys.verify(db,value)
    with pytest.raises(ValueError):access_keys.manage(db,service.identity,'invalid')
    with pytest.raises(WorkspaceError):access_keys.manage(db,Identity('user_other',None,None,'explorer'),grant['id'])


def test_workbench_authentication_uses_revoked_key_checks_and_personal_billing(service,monkeypatch):
    from services.api import workbench,access_keys
    from types import SimpleNamespace as NS
    db=service.store('scenes').db
    key=access_keys.create(db,service.identity,'Agent',['read'],1)['key']
    monkeypatch.setattr(workbench,'database',lambda:db)
    monkeypatch.setattr(workbench.clerk_billing,'_profile',lambda subject:NS(banned=False,locked=False))
    monkeypatch.setattr(workbench.clerk_billing,'enabled',lambda:True)
    monkeypatch.setattr(workbench.clerk_billing,'plan',lambda subject:'researcher')
    verified=workbench.actor('Bearer '+key)
    assert verified.user_id==service.identity.user_id and verified.plan=='researcher' and verified.token_scopes==('read',)
    monkeypatch.setattr(workbench.clerk_billing,'_profile',lambda subject:NS(banned=True))
    with pytest.raises(WorkspaceError):workbench.actor('Bearer '+key)
    monkeypatch.setattr(workbench,'authenticate',lambda token:Identity('user_browser','org_acme','org:member','explorer'))
    assert workbench.actor('Bearer session').plan=='explorer'
    monkeypatch.setattr(workbench,'authenticate',lambda token:Identity('user_browser',None,None,'explorer'))
    assert workbench.actor('Bearer session').plan=='researcher'
    monkeypatch.setattr(workbench,'library',lambda identity,kind:service._stores[kind])
    assert Workbench(service.identity).store('media') is service.store('media')
    with pytest.raises(ValueError):service.execute('create_scenes',{'name':' '*3,'scene':scene()},'invalid-name-idempotency')
    with pytest.raises(ValueError):service.execute('list_scenes',[])
    with pytest.raises(ValueError):use_object(scene(),spark.procedural_object('robot'),'<script>',4,5)
    result=service.execute('prepare_scene',{'scene':scene()});assert result['stage_metres']==[16,14]
    assert service.execute('render_video_preview',{'scene':scene(),'duration_s':1,'width':160,'height':120})['mime_type']=='image/gif'
    spec=spark.procedural_object('box');assert service.execute('validate_object',{'spec':spec})['spec']==spec
    monkeypatch.setattr(spark,'design_custom_object',lambda *a:(spec,{'fixture':True}))
    assert service.execute('generate_object',{'description':'box'},'object-model-idempotency')['spec']==spec
    monkeypatch.setattr(workbench,'describe_paths',lambda *a:{'scene':scene()})
    assert service.execute('describe_paths',{'scene':scene(),'description':'move right'},'path-model-idempotency')['scene']==scene()
    assert service.execute('predict_path',{'points':[[0,1,1],[1,2,1],[2,3,1]]})['velocity']==[1,0]
    with pytest.raises(ValueError):service.execute('get_model_request',{'request_key':'bad'})
    with pytest.raises(ValueError):service.execute('list_media',{'limit':101})


def test_http_error_mapping_billing_and_key_management(service,monkeypatch):
    from services.api import workbench_http as wh
    from integrations import billing
    class Headers(dict):pass
    class Handler:
        def __init__(self,payload,headers=None):
            self.payload=payload;self.headers=Headers({'Content-Length':str(len(json.dumps(payload))),'Content-Type':'application/json','Authorization':'Bearer fixture',**(headers or {})})
            self.path='/api/v1/paths/plan';self.result=None
            self.rfile=io.BytesIO(json.dumps(payload).encode())
        def _body(self):return self.payload
        def _send(self,*args):self.result=args
    monkeypatch.setattr(wh,'actor',lambda value:service.identity)
    monkeypatch.setattr(Workbench,'store',lambda self,kind:service._stores[kind])
    cases=[('/api/v1/account','POST',{},None,405),('/api/v1/scenes/list','GET',{},None,405),
      ('/api/v1/scenes/list','POST',{}, {'X-Workspace-Organization':'org_other'},409),
      ('/api/v1/scenes/list','POST',{}, {'Content-Length':'wrong'},400),
      ('/api/v1/scenes/list','POST',{}, {'Content-Length':'999999'},413),
      ('/api/v1/scenes/list','POST',{}, {'Content-Type':'text/html'},415),
      ('/api/v1/scenes/list','POST',[],None,400),('/api/paths/plan','GET',{},None,405),
      ('/api/paths/plan','POST',{},None,400),('/api/paths/predict','POST',{},None,400),
      ('/api/paths/plan','POST',{}, {'Origin':'https://evil.example'},403)]
    for route,method,payload,headers,wanted in cases:
        handler=Handler(payload,headers);assert wh.handle(handler,route,method);assert handler.result[0]==wanted,(route,handler.result)
    monkeypatch.setattr(wh.clerk_billing,'enabled',lambda:False)
    handler=Handler({});wh.handle(handler,'/api/v1/billing/portal','POST');assert handler.result[0]==503
    monkeypatch.setattr(wh.clerk_billing,'enabled',lambda:True)
    monkeypatch.setattr(wh.clerk_billing,'checkout',lambda *a:{'url':'https://checkout.stripe.com/test'})
    monkeypatch.setattr(wh.clerk_billing,'portal',lambda *a:{'url':'https://billing.stripe.com/test'})
    for route in ['/api/v1/billing/checkout','/api/v1/billing/portal']:
        handler=Handler({});wh.handle(handler,route,'POST');assert handler.result[0]==200
    monkeypatch.setattr(wh,'actor',lambda _:Identity('user_org','org_team','org:admin','team'))
    handler=Handler({});wh.handle(handler,'/api/v1/billing/checkout','POST');assert handler.result[0]==409
    monkeypatch.setattr(wh,'actor',lambda _:Identity('user_key',None,None,'researcher',('read',)))
    handler=Handler({});wh.handle(handler,'/api/v1/billing/portal','POST');assert handler.result[0]==403
    monkeypatch.setattr(wh,'actor',lambda _:service.identity)
    monkeypatch.setattr('services.api.workspace_http.database',lambda:service.store('scenes').db)
    handler=Handler({'name':'HTTP key','scopes':['read']});wh.handle(handler,'/api/v1/keys/create','POST');assert handler.result[0]==200
    key_id=handler.result[1]['id']
    for route,payload in [('/api/v1/keys/list',{}),('/api/v1/keys/revoke',{'id':key_id})]:
        handler=Handler(payload);wh.handle(handler,route,'POST');assert handler.result[0]==200
    monkeypatch.setattr(Workbench,'execute',lambda *a:(_ for _ in ()).throw(spark.BlockedCredentials('secret key missing')))
    handler=Handler({});wh.handle(handler,'/api/v1/scenes/list','POST');assert handler.result==(503,{'error':'model_provider_not_configured'})
    monkeypatch.setattr(Workbench,'execute',lambda *a:(_ for _ in ()).throw(spark.ModelError('private model error')))
    handler=Handler({});wh.handle(handler,'/api/v1/scenes/list','POST');assert handler.result[0]==502 and 'private' not in json.dumps(handler.result)
    monkeypatch.setattr(Workbench,'execute',lambda *a:(_ for _ in ()).throw(RuntimeError('private credential')))
    handler=Handler({});wh.handle(handler,'/api/v1/scenes/list','POST');assert handler.result==(503,{'error':'workbench_service_unavailable'})
    monkeypatch.setattr(wh.billing,'verify_webhook',lambda *a:{'fixture':True})
    monkeypatch.setattr(wh.clerk_billing,'webhook',lambda *a:{'received':True})
    handler=Handler({});wh.handle(handler,'/api/billing/webhook','POST');assert handler.result[0]==200
    handler=Handler({}, {'Content-Length':'2000000'});wh.handle(handler,'/api/billing/webhook','POST');assert handler.result[0]==413


def test_stationary_video_reports_actual_encoded_frames():
    document=scene();document['objects']=document['objects'][1:]
    result=render_video_preview(document,1,6,160,120)
    decoded=Image.open(io.BytesIO(base64.b64decode(result['data_url'].split(',')[1])))
    assert result['frame_count']==decoded.n_frames
    assert sum(result['frame_durations_ms'])/1000==result['duration_s']
    assert result['requested_frames']==6


def test_checkout_probe_requires_real_writable_storage(service,monkeypatch):
    from integrations import clerk_billing
    from services.api import firestore_scenes
    class Probe:
        def __init__(self):self.closed=False
        def close(self):self.closed=True
    db=Probe();calls=[]
    monkeypatch.setattr(firestore_scenes,'client',lambda:db)
    class Storage:
        def __init__(self,*args):calls.append(args)
        def consume_request(self,**kwargs):calls.append(kwargs)
    monkeypatch.setattr(firestore_scenes,'Scenes',Storage)
    monkeypatch.setenv('WORKSPACE_AUDIT_SECRET','test-secret-'*4)
    clerk_billing._ensure_storage('user_verified')
    assert db.closed and calls[1]=={'maximum':5}


def test_every_workbench_tool_matches_a_published_rest_operation():
    from pathlib import Path
    from services.api.workbench_http import ROUTES
    from services.api.workbench_contract import schemas
    from services.api.mcp import TOOLS
    spec=json.loads((Path(__file__).resolve().parents[1]/'apps/web/openapi.json').read_text())
    available=schemas({'$ref':'#/components/schemas/EditableScene'})
    assert set(ROUTES.values())==set(available)
    tools={tool['name']:tool for tool in TOOLS}
    for route,operation in ROUTES.items():
        assert spec['paths'][route]['post']['operationId']==operation
        assert operation in tools and spec['components']['schemas']['Workbench_'+operation]==available[operation]
    assert len({tool['name'] for tool in TOOLS})==len(TOOLS)
    from services.api.physical import SCHEMAS as PHYSICAL_SCHEMAS
    assert len(TOOLS)==10+len(available)+len(PHYSICAL_SCHEMAS)


def test_existing_website_object_routes_share_the_new_firestore_library(service,monkeypatch):
    from services.api import workspace_http
    from services.api.server import H
    monkeypatch.setenv('SCENE_STORE','firestore')
    monkeypatch.setenv('WORKSPACE_AUDIT_SECRET',service.store('objects').secret)
    monkeypatch.setenv('CLERK_AUTHORIZED_PARTIES','https://frontiersight.example')
    monkeypatch.setattr(workspace_http,'identity',lambda handler:service.identity)
    monkeypatch.setattr(workspace_http,'database',lambda:service.store('objects').db)
    server=ThreadingHTTPServer(('127.0.0.1',0),H);threading.Thread(target=server.serve_forever,daemon=True).start()
    base='http://127.0.0.1:'+str(server.server_port)
    def request(path,data=None):
        req=urllib.request.Request(base+path,data=json.dumps(data).encode() if data is not None else None,
           headers={'Content-Type':'application/json','Idempotency-Key':uuid.uuid4().hex})
        try:
            with urllib.request.urlopen(req) as r:return r.status,json.load(r)
        except urllib.error.HTTPError as error:return error.code,json.load(error)
    try:
        spec=spark.procedural_object('crate')
        status,saved=request('/api/objects',{'spec':spec,'image':png()})
        assert status==201,saved
        rows=request('/api/objects')[1]['objects'];assert rows[0]['spec']==spec and rows[0]['version']==1
        shared=service.execute('get_objects',{'id':saved['id']})['record']
        assert shared['payload']['spec']==spec
        assert request('/api/objects/delete',{'id':saved['id'],'expectedVersion':1})[0]==200
        assert request('/api/objects/delete')[0]==405
        assert request('/api/scene-context')[1]['userId']==service.identity.user_id
    finally:server.shutdown();server.server_close()


def test_provider_keys_are_encrypted_and_apply_only_to_their_request(service,monkeypatch):
    from services.api.workbench import provider_key
    from integrations.meta.credentials import api_key,using_key
    store=service.store('scenes');secret='a-test-encryption-secret-that-is-long-enough'
    monkeypatch.setenv('BYOK_ENCRYPTION_KEY',secret)
    key='LLM_fixture_private_key_123456789'
    assert provider_key(store,service.identity,'save',key)['last4']=='6789'
    stored=store.root.collection('provider_keys').document('meta').get().to_dict()
    assert key not in json.dumps(stored) and 'ciphertext' in stored
    assert provider_key(store,service.identity,'load')==key
    assert provider_key(store,service.identity,'status')=={'configured':True,'last4':'6789'}
    monkeypatch.setenv('MODEL_API_KEY','host-fixture-key')
    seen=[]
    monkeypatch.setattr(spark,'design_custom_object',lambda *args:(seen.append(api_key()) or spark.procedural_object('robot'),{}))
    service.execute('generate_object',{'description':'robot'},'private-key-model-request')
    assert seen==[key] and api_key()=='host-fixture-key'
    with pytest.raises(RuntimeError):
        with using_key('isolated-fixture'):assert api_key()=='isolated-fixture';raise RuntimeError('abort')
    assert api_key()=='host-fixture-key'
    with pytest.raises(WorkspaceError):provider_key(store,Identity('user_free',None,None,'explorer'),'save',key)
    with pytest.raises(WorkspaceError):provider_key(store,Identity('user_member','org_team','org:member','team'),'delete')
    with pytest.raises(ValueError):provider_key(store,service.identity,'save','bad')
    monkeypatch.delenv('BYOK_ENCRYPTION_KEY')
    for op in ['save','load']:
        with pytest.raises(WorkspaceError):provider_key(store,service.identity,op,key)
    monkeypatch.setenv('BYOK_ENCRYPTION_KEY','different-test-key')
    with pytest.raises(WorkspaceError):provider_key(store,service.identity,'load')
    assert provider_key(store,service.identity,'delete')=={'configured':False}
    assert provider_key(store,service.identity,'load') is None


def test_candidate_workers_receive_the_request_key_without_global_environment_changes(monkeypatch):
    from integrations.meta.credentials import api_key,using_key
    monkeypatch.setenv('MODEL_API_KEY','host-key-fixture')
    observed=[]
    def call(*args,**kwargs):
        observed.append(api_key());return json.dumps(scene()),{'model':'fixture'}
    monkeypatch.setattr(spark,'_call',call)
    with using_key('tenant-key-fixture'):
        generated,meta=spark.generate_scene('A warehouse with a robot and a shelf',candidates=3)
    assert len(generated['objects'])==2 and observed==['tenant-key-fixture']*3
    assert api_key()=='host-key-fixture'


def test_preparation_keeps_predicted_routes_distinct_from_observed_data(service):
    document=scene();document['objects'][0]['path_source']='PREDICTED'
    result=service.execute('prepare_scene',{'scene':document})
    assert result['tracks'][0]['source']=='PREDICTED'
    assert result['tracks'][1]['source']=='USER_CREATED'
