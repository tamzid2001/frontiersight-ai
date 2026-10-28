"""Scene edits, browser/API parity, and actual HTTP/MCP transport checks."""
from copy import deepcopy
import json
import shutil
import subprocess
from pathlib import Path
import pytest
from engine.scene_edit import resize_scene, reposition_scene, validate_document, fit_path, translate_path
from engine.curves import Path as CurvePath

ROOT=Path(__file__).resolve().parents[1]

def scene(curve='straight',mode='stop'):
    return {'name':'Example','stage_metres':[16,14],'objects':[
        {'id':'forklift-1','category':'forklift','radius':.5,'speed':1.4,'delay':.25,'mode':mode,'curve':curve,
         'waypoints':[[2,2],[8,7],[14,12]],'custom':{'reference':'owned-object'}}]}


def test_resize_atomic_preserves_physical_properties_and_identity():
    original=scene();before=deepcopy(original)
    out=resize_scene(original,8,7)
    assert out['scene']['stage_metres']==[8,7]
    assert out['scene']['objects'][0]['waypoints']==[[1,1],[4,3.5],[7,6]]
    for key in ('id','radius','speed','delay','custom'):
        assert out['scene']['objects'][0][key]==before['objects'][0][key]
    assert out['persisted'] is False and out['source']=='DETERMINISTIC'
    assert original==before
    original['objects'][0]['radius']=4
    with pytest.raises(ValueError):resize_scene(original,6,6)
    assert original['stage_metres']==[16,14]


@pytest.mark.parametrize('curve,mode',[('straight','stop'),('smooth','stop'),('smooth','loop'),('smooth','pingpong')])
def test_resized_curve_and_footprint_fit_floor(curve,mode):
    out=resize_scene(scene(curve,mode),6,9)['scene'];obj=out['objects'][0]
    path=CurvePath(obj['waypoints'],curve,mode=='loop')
    assert all(.5-1e-8<=p.x<=5.5+1e-8 and .5-1e-8<=p.y<=8.5+1e-8 for p in path.points)


def test_reposition_targets_first_waypoint_and_clamps_without_path_deformation():
    original=scene();before=deepcopy(original)
    out=reposition_scene(original,'forklift-1',100,3)
    obj=out['scene']['objects'][0]
    assert out['clamped'] and obj['waypoints'][0]==[3.5,3]
    assert obj['waypoints'][2][0]-obj['waypoints'][0][0]==12
    assert out['applied_translation']==[1.5,1]
    assert original==before and out['persisted'] is False
    exact=reposition_scene(original,'forklift-1',3,3)
    assert not exact['clamped'] and exact['scene']['objects'][0]['waypoints'][0]==[3,3]


@pytest.mark.parametrize('bad',[None,[],{'objects':[]}, {'stage_metres':[6,6],'objects':None}])
def test_invalid_documents_fail(bad):
    with pytest.raises(ValueError):validate_document(bad)


@pytest.mark.parametrize('size',[[0,6],[61,6],[True,6],[float('nan'),6],[10**1000,6],[6],None])
def test_invalid_dimensions_fail(size):
    s=scene();s['stage_metres']=size
    with pytest.raises(ValueError):validate_document(s)


@pytest.mark.parametrize('patch',[{'id':''},{'id':4},{'id':'a','object_id':'b'},{'radius':True},{'radius':100},
                                  {'waypoints':[[1]]},{'waypoints':[[float('inf'),2]]},
                                  {'waypoints':[[10001,2]]},{'curve':'invalid'},{'mode':'invalid'}])
def test_invalid_objects_fail(patch):
    s=scene();s['objects'][0].update(patch)
    with pytest.raises(ValueError):validate_document(s)


def test_collection_budgets_duplicate_ids_and_missing_targets():
    s=scene();s['objects']*=2
    with pytest.raises(ValueError):validate_document(s)
    s=scene();s['objects']*=25
    with pytest.raises(ValueError):validate_document(s)
    s=scene();s['objects'][0]['waypoints']*=9
    with pytest.raises(ValueError):validate_document(s)
    s=scene();s['objects']=['invalid']
    with pytest.raises(ValueError):validate_document(s)
    for target in ('absent',None):
        with pytest.raises(ValueError):reposition_scene(scene(),target,1,1)
    with pytest.raises(ValueError):reposition_scene(scene(),'forklift-1',float('nan'),1)


def test_empty_scene_and_alias_id_and_cache_removal():
    assert resize_scene({'stage_metres':[16,14],'objects':[]},6,6)['scene']['objects']==[]
    s=scene();o=s['objects'][0];o['object_id']=o.pop('id');o['_res']={'stale':True};o['_prof']={'stale':True}
    out=reposition_scene(s,'forklift-1',3,3)['scene']['objects'][0]
    assert out['object_id']=='forklift-1' and '_res' not in out and '_prof' not in out
    assert fit_path([], [6,6],1)==[]
    assert fit_path([[1,1]], [6,6],1)==[[1,1]]
    with pytest.raises(ValueError):translate_path([[0,0],[20,20]],0,0,[6,6],1)


def test_browser_geometry_matches_api_geometry():
    node=shutil.which('node')
    if not node:pytest.skip('Node runtime unavailable for cross-language parity')
    payload={'points':[[0,0],[16,14]],'from':[16,14],'to':[6,8],'radius':1}
    script="const e=require('./apps/web/stage-edit-core.js');let p=JSON.parse(process.argv[1]);console.log(JSON.stringify({resized:e.resizePath(p.points,p.from,p.to,p.radius),moved:e.translatePath([[2,2],[5,4]],100,-100,[10,8],1)}));"
    observed=json.loads(subprocess.check_output([node,'-e',script,json.dumps(payload)],cwd=ROOT,text=True))
    scaled=[[p[a]*payload['to'][a]/payload['from'][a] for a in range(2)] for p in payload['points']]
    expected=fit_path(scaled,payload['to'],payload['radius'])
    for actual,want in zip(observed['resized'],expected):assert actual==pytest.approx(want,abs=1e-9)
    assert observed['moved']==translate_path([[2,2],[5,4]],100,-100,[10,8],1)


def test_actual_http_api_mcp_and_openapi_share_operations(monkeypatch):
    monkeypatch.setenv("SCENE_STORE","firestore")
    import threading,urllib.request,urllib.error
    from http.server import ThreadingHTTPServer
    from services.api.server import H
    server=ThreadingHTTPServer(('127.0.0.1',0),H);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    base=f'http://127.0.0.1:{server.server_address[1]}'
    def request(path,payload=None):
        data=json.dumps(payload).encode() if payload is not None else None
        req=urllib.request.Request(base+path,data=data,headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=10) as response:return response.status,json.load(response)
    try:
        payload={'scene':scene(),'width':8,'height':7}
        status,api=request('/api/scenes/resize',payload)
        assert status==200 and api==resize_scene(**payload)
        _,mcp=request('/api/mcp',{'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':'resize_scene','arguments':payload}})
        assert mcp['result']['structuredContent']==api
        position={'scene':scene(),'object_id':'forklift-1','x':3,'y':3}
        _,api=request('/api/scenes/reposition',position)
        _,mcp=request('/api/mcp',{'jsonrpc':'2.0','id':2,'method':'tools/call','params':{'name':'reposition_scene','arguments':position}})
        assert api==mcp['result']['structuredContent']==reposition_scene(**position)
        _,listing=request('/api/mcp',{'jsonrpc':'2.0','id':3,'method':'tools/list'})
        assert {'resize_scene','reposition_scene'} <= {tool['name'] for tool in listing['result']['tools']}
        _,error=request('/api/mcp',{'jsonrpc':'2.0','id':4,'method':'tools/call','params':{'name':'resize_scene','arguments':{}}})
        assert error['result']['isError'] is True
        for path,payload in [('/api/scenes/resize',{}),('/api/scenes/reposition',position|{'object_id':'missing'}),('/api/scenes/resize',[])]:
            with pytest.raises(urllib.error.HTTPError) as failure:request(path,payload)
            assert failure.value.code==400
        for path in ['/openapi.json','/api/index?ep=openapi']:
            _,spec=request(path);assert spec['openapi']=='3.1.0'
            assert '/api/scenes/resize' in spec['paths'] and '/api/scenes/reposition' in spec['paths']
    finally:
        server.shutdown();server.server_close();thread.join(timeout=3)


def test_openapi_is_valid_and_mcp_schemas_are_the_published_contract():
    from openapi_spec_validator import validate
    from jsonschema import Draft202012Validator, ValidationError
    from services.api.mcp import TOOLS
    spec=json.loads((ROOT/'apps/web/openapi.json').read_text());validate(spec)
    for name,payload in [('resize_scene',{'scene':scene(),'width':8,'height':7}),
                         ('reposition_scene',{'scene':scene(),'object_id':'forklift-1','x':3,'y':3})]:
        schema=next(tool['inputSchema'] for tool in TOOLS if tool['name']==name)
        Draft202012Validator.check_schema(schema);Draft202012Validator(schema).validate(payload)
        with pytest.raises(ValidationError):Draft202012Validator(schema).validate({})


def test_unplaced_objects_can_be_resized_and_placed_by_api():
    s=scene();s['objects'][0]['waypoints']=[]
    assert resize_scene(s,8,7)['scene']['objects'][0]['waypoints']==[]
    assert reposition_scene(s,'forklift-1',3,4)['scene']['objects'][0]['waypoints']==[[3,4]]
    assert reposition_scene(s,'forklift-1',100,-100)['clamped'] is True


def test_stdio_bridge_exposes_same_scene_edits():
    import sys
    payload={'scene':scene(),'width':8,'height':7}
    request={'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':'resize_scene','arguments':payload}}
    result=subprocess.run([sys.executable,'scripts/mcp_stdio.py'],cwd=ROOT,input=json.dumps(request)+'\n',text=True,capture_output=True,check=True,timeout=10)
    assert json.loads(result.stdout)['result']['structuredContent']==resize_scene(**payload)
    assert translate_path([],1,1,[6,6])=={'points':[],'dx':0,'dy':0,'clamped':False}


def test_mcp_rejects_malformed_envelopes_without_crashing_bridge():
    from services.api.mcp import handle_jsonrpc
    for payload in ([], 1, "invalid", None):
        assert handle_jsonrpc(payload)["error"]["code"] == -32600
    for params in ([], 1, "invalid", None):
        request = {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": params}
        assert handle_jsonrpc(request)["error"]["code"] == -32602


def test_prepare_preserves_floor_objects_custom_appearance_and_motion():
    from engine.scene_edit import prepare_scene, scene_to_scenario
    from engine.scenarios import scenario_to_dict
    original=scene('smooth','pingpong');before=deepcopy(original)
    original['objects'][0]['_res']={'derived':'discard'}
    prepared=prepare_scene(original)
    assert prepared['stage_metres']==[16,14]
    assert prepared['objects'][0]['custom']==before['objects'][0]['custom']
    assert prepared['objects'][0]['waypoints']==before['objects'][0]['waypoints']
    assert '_res' not in prepared['objects'][0]
    assert prepared['tracks'][0]['object_id']=='forklift-1'
    assert prepared['tracks'][0]['radius']==.5
    assert prepared['tracks'][0]['points'][0]==[0.0,2.0,2.0]
    assert prepared['tracks'][0]['points'][-1][0]<=20
    assert prepared==scenario_to_dict(scene_to_scenario(original))
    changed=resize_scene(before,8,7)['scene']
    assert prepare_scene(changed)['scene_digest']!=prepared['scene_digest']
    assert before['objects'][0]['waypoints']==original['objects'][0]['waypoints']


@pytest.mark.parametrize('patch',[
    {'objects':[]}, {'objects':[{'id':'x','waypoints':[]}]},
    {'objects':[{'id':'x','waypoints':[[1,1]],'category':'unknown'}]},
    {'objects':[{'id':'x','waypoints':[[1,1]],'speed':-1}]},
    {'objects':[{'id':'x','waypoints':[[1,1]],'delay':11}]},
])
def test_unplayable_scenes_are_rejected(patch):
    from engine.scene_edit import prepare_scene
    with pytest.raises(ValueError):prepare_scene(scene()|patch)


def test_scene_counterfactual_retains_context_and_respects_target():
    from engine.scene_edit import prepare_scene, simulate_scene
    from services.api.mcp import call_tool
    s=scene();s['objects'].append({'id':'shelf-1','category':'shelf','speed':0,'radius':1,'waypoints':[[8,7]]})
    s['objects'].append({'id':'other','category':'pedestrian','radius':.3,'waypoints':[[4,4]]})
    out=simulate_scene(s,'forklift-1','shelf-1',mc_runs=0)
    assert out['stage_metres']==s['stage_metres'] and out['objects']==s['objects']
    assert set(out['results'])=={'shelf-1'}
    assert out['scene_digest']==prepare_scene(s)['scene_digest']
    assert call_tool('simulate_counterfactual',{'scene':s,'agent_id':'forklift-1','target_id':'shelf-1','mc_runs':0})['structuredContent']==out
    assert call_tool('sample_paths',{'scene':s})['structuredContent']==prepare_scene(s)
    for agent,target in [('missing',None),('forklift-1','missing'),('forklift-1','forklift-1')]:
        with pytest.raises(ValueError):simulate_scene(s,agent,target,mc_runs=0)
    with pytest.raises(ValueError):call_tool('sample_paths',{'scene':s,'objects':s['objects']})
    with pytest.raises(ValueError):call_tool('simulate_counterfactual',{'scene':s,'scenario':'safe-passing'})


def test_prepared_http_scene_and_mcp_have_identical_geometry(monkeypatch,tmp_path):
    monkeypatch.delenv("MODEL_API_KEY",raising=False)
    monkeypatch.setenv("DATABASE_URL",f"sqlite:///{tmp_path}/scene.db")
    from services.api import store
    store._conn=None
    import threading,urllib.request
    from http.server import ThreadingHTTPServer
    from services.api.server import H
    from services.api.mcp import TOOLS
    from jsonschema import Draft202012Validator
    from engine.scene_edit import prepare_scene
    s=scene();s['objects'].append({'id':'shelf-1','category':'shelf','speed':0,'radius':1,'waypoints':[[8,7]]})
    server=ThreadingHTTPServer(('127.0.0.1',0),H);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    def post(path,body):
        req=urllib.request.Request(f'http://127.0.0.1:{server.server_port}'+path,json.dumps(body).encode(),headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=10) as response:return json.load(response)
    try:
        assert post('/api/scenes/prepare',{'scene':s})==prepare_scene(s)
        arguments={'scene':s,'agent_id':'forklift-1','target_id':'shelf-1','mc_runs':0}
        result=post('/api/counterfactual-custom',arguments)
        mcp=post('/api/mcp',{'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':'simulate_counterfactual','arguments':arguments}})
        assert result==mcp['result']['structuredContent']
        assert result['stage_metres']==s['stage_metres']
        analyzed=post('/api/analyze-custom',{'scene':s})
        assert analyzed['scenario']['stage_metres']==s['stage_metres']
        assert analyzed['scenario']['objects']==s['objects']
        assert analyzed['scenario']['scene_digest']==prepare_scene(s)['scene_digest']
        assert analyzed['run']['findings']['pairs']
        for name,args in [('sample_paths',{'scene':s}),('simulate_counterfactual',arguments)]:
            schema=next(tool['inputSchema'] for tool in TOOLS if tool['name']==name)
            Draft202012Validator.check_schema(schema);Draft202012Validator(schema).validate(args)
    finally:
        server.shutdown();server.server_close();thread.join(timeout=3)
