from copy import deepcopy
import json
import urllib.error
import urllib.request

import pytest

from engine.demos3d import warehouse
from engine.world3d import digest
from engine.world3d_schema import validate
from services.api import physical, mcp
from test_physical_api import http_server


@pytest.mark.parametrize('with_baseline',[False,True])
def test_recomputed_project_evidence_http_mcp_parity_and_integrity(http_server,with_baseline):
    scene=warehouse()
    request={'scene':scene,'document_id':'original-demo','scene_revision':7}
    if with_baseline:
        request['baseline']=deepcopy(scene)
        scene['objects'][2]['joint']['start_s']=2
    original=deepcopy(request)
    direct=physical.execute('export_project_evidence_3d',request)
    raw=urllib.request.Request(http_server+'/api/v2/evidence/project',data=json.dumps(request).encode(),headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(raw) as response:rest=json.load(response)
    via_mcp=json.loads(mcp.call_tool('export_project_evidence_3d',request)['content'][0]['text'])
    assert direct==rest==via_mcp and request==original
    validate(physical.OUTPUT_SCHEMAS['export_project_evidence_3d'],direct)
    assert digest(direct['packet'])==direct['packet_sha256']
    assert direct['packet']['document_context']=={'id':'original-demo','revision':7,'authority':'caller_supplied_not_authenticated'}
    assert direct['signature'] is None and direct['persisted'] is False
    if with_baseline:
        result=direct['packet']['result']
        assert result['changed_object_ids']==['forks']
        assert result['baseline_digest']!=result['alternative_digest']
        assert result['baseline']['frames']!=result['counterfactual']['frames']
    else:assert direct['packet']['kind']=='scene_simulation'
    changed=deepcopy(direct['packet']);changed['document_context']['revision']=8
    assert digest(changed)!=direct['packet_sha256']


@pytest.mark.parametrize('change',[{'scene_revision':-1},{'document_id':''},{'document_id':'x'*101},
    {'scene_revision':1.1},{'user_id':'another-tenant'},{'scene':{}},{'baseline':{}}])
def test_invalid_project_context_is_rejected(change):
    request={'scene':warehouse(),'document_id':'demo','scene_revision':0,**change}
    with pytest.raises(ValueError):physical.execute('export_project_evidence_3d',request)


def test_new_frontend_modules_use_bounded_deployment_asset_routes(http_server):
    for name in ['guided-lab.mjs','guided-lab-core.mjs','guided-lab.css','world-visuals.mjs']:
        with urllib.request.urlopen(http_server+'/api/index?ep=labasset&file='+name) as response:
            assert response.status==200 and len(response.read())>0
    with pytest.raises(urllib.error.HTTPError):
        urllib.request.urlopen(http_server+'/api/index?ep=labasset&file=../../../private-key')


def test_editor_document_identity_is_preserved_as_context_not_a_resource_lookup():
    identity='Warehouse revision – 測定'
    result=physical.execute('export_project_evidence_3d',{'scene':warehouse(),'document_id':identity,'scene_revision':0})
    assert result['packet']['document_context']['id']==identity
