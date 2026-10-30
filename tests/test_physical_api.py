import json
import threading
import urllib.request
import urllib.error
from http.server import ThreadingHTTPServer
from copy import deepcopy
import pytest
from engine.demos3d import flying,warehouse
from services.api import physical,mcp
from services.api.server import H
from integrations.meta import spark
from integrations.meta.physics_edit import propose_physics


@pytest.fixture
def http_server(monkeypatch):
    monkeypatch.setenv('APP_BASE_URL','http://localhost')
    server=ThreadingHTTPServer(('127.0.0.1',0),H);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    yield 'http://127.0.0.1:'+str(server.server_port)
    server.shutdown();server.server_close();thread.join()


def test_actual_http_mcp_and_direct_parity(http_server):
    scene=flying();body=json.dumps({'scene':scene}).encode()
    with urllib.request.urlopen(urllib.request.Request(http_server+'/api/v2/simulations/run',data=body,headers={'Content-Type':'application/json'})) as response:
        result=json.load(response)
    direct=physical.execute('simulate_scene_3d',{'scene':scene})
    mcp_result=mcp.call_tool('simulate_scene_3d',{'scene':scene})
    assert result==direct==json.loads(mcp_result['content'][0]['text'])
    capabilities=json.load(urllib.request.urlopen(http_server+'/api/v2/capabilities'))
    assert capabilities['physical_actuation'] is False
    for path in ('/physical-intelligence','/physical-intelligence.mjs','/physical-intelligence.css'):
        with urllib.request.urlopen(http_server+path) as response: assert response.status==200
    bad=deepcopy(scene);bad['schema_version']='0'
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(urllib.request.Request(http_server+'/api/v2/simulations/run',data=json.dumps({'scene':bad}).encode(),headers={'Content-Type':'application/json'}))
    assert e.value.code==400
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(urllib.request.Request(http_server+'/api/v2/simulations/run',data=body,headers={'Origin':'https://evil.test','Content-Type':'application/json'}))
    assert e.value.code==403


def test_shared_contract_operations_and_integrity():
    scene=warehouse()
    for name in physical.SCHEMAS: assert any(t['name']==name for t in mcp.TOOLS)
    assert physical.execute('get_scene_3d',{'demo':'warehouse'})['scene']==scene
    assert physical.execute('prepare_scene_3d',{'scene':scene})['scene']==scene
    profile=scene['objects'][0]['physics']
    assert physical.execute('validate_physics_profile',{'profile':profile})['validated']
    report=physical.execute('export_evidence_packet_3d',{'scene':scene})
    from engine.world3d import digest
    assert report['packet_sha256']==digest(report['packet']) and report['signature'] is None
    assert physical.execute('calibrate_scene',{'pixel':[0,0]})['status']=='DEPTH_UNAVAILABLE'
    assert physical.execute('estimate_kinematics_3d',{'points':[{'t_s':0,'position':[0,0,0]},{'t_s':1,'position':[1,0,0]}]})['coordinate_dimensions']==3
    with pytest.raises(ValueError):physical.execute('simulate_scene_3d',{'scene':scene,'eval':'x'})


def test_model_proposal_never_mutates_scene(monkeypatch):
    profile=warehouse()['objects'][0]['physics'];original=deepcopy(profile)
    changed=deepcopy(profile);changed['max_payload_kg']=900
    def invoke(prompt,**kw):
        assert kw['timeout']==20 and kw['retries']==0
        return json.dumps({'profile':changed,'assumptions':['Declared payload capability'],'missing_parameters':[]}),{'fixture':True}
    monkeypatch.setattr(spark,'_call',invoke)
    result=propose_physics(profile,'Use a 900 kg payload capacity')
    assert result['profile']['max_payload_kg']==900 and not result['applied'] and result['requires_approval']
    assert profile==original
    monkeypatch.setattr(spark,'_call',lambda *a,**k:('{"profile":{"eval":"bad"}}',{}))
    with pytest.raises(spark.ModelError):propose_physics(profile,'Change gravity')


def test_sdk_v2_and_openapi_roundtrip(http_server):
    from sdk.frontiersight import FrontierSight
    from pathlib import Path
    from scripts.build_physical_contract import build
    client=FrontierSight(base_url=http_server,token='')
    scene=client.call('scenes/demo',{'demo':'flying'},api_version='v2')['scene']
    assert client.call('simulations/run',{'scene':scene},api_version='v2')==physical.execute('simulate_scene_3d',{'scene':scene})
    spec=json.loads((Path(__file__).resolve().parents[1]/'apps/web/openapi.json').read_text())
    assert build(deepcopy(spec))==spec
    for route,name in physical.ROUTES.items():
        assert spec['paths'][route]['post']['requestBody']['content']['application/json']['schema']==physical.SCHEMAS[name]
