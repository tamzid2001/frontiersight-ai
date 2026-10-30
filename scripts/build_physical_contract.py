"""Regenerate v2 and additive v1 contracts from canonical Python schemas."""
import json
from pathlib import Path
from services.api.physical import ROUTES, SCHEMAS, DESCRIPTIONS
from services.api.workbench_http import ROUTES as WORKBENCH_ROUTES
from services.api.workbench_contract import schemas,DESCRIPTIONS as WORKBENCH_DESCRIPTIONS
from engine.world3d_schema import SCENE,PROFILE


def build(spec):
    spec['components']['schemas'].update(Scene3D=SCENE,PhysicsProfile3D=PROFILE)
    for route,name in ROUTES.items():
        spec['paths'][route]={'post':{'operationId':name,'summary':DESCRIPTIONS[name],
            'requestBody':{'required':True,'content':{'application/json':{'schema':SCHEMAS[name]}}},
            'responses':{'200':{'description':'Deterministic result with explicit provenance and numerical methods','content':{'application/json':{'schema':{'type':'object'}}}},
                         '400':{'description':'Invalid schema, unsupported dynamics, calibration failure or compute budget'},
                         '403':{'description':'Origin denied'},'429':{'description':'Per-instance request limit; no automatic retry'}}}}
    spec['paths']['/api/v2/capabilities']={'get':{'operationId':'physical_capabilities','summary':'Supported software capabilities, budgets and unverified hardware status',
                                                'responses':{'200':{'description':'Capability record'}}}}
    published=schemas({'$ref':'#/components/schemas/EditableScene'})
    for name,request_schema in published.items():
        spec['components']['schemas']['Workbench_'+name]=request_schema
    for route,name in WORKBENCH_ROUTES.items():
        if route not in spec['paths']:
            spec['paths'][route]={'post':{'operationId':name,'summary':WORKBENCH_DESCRIPTIONS[name],
                'security':[{'ClerkBearer':[]}],'parameters':[{'in':'header','name':'Idempotency-Key','schema':{'type':'string'},'required':True}],
                'responses':{'200':{'description':'Validated proposal, no scene mutation'},'400':{'description':'Invalid request'},'401':{'description':'Authentication required'},
                             '402':{'description':'Researcher plan required'},'409':{'description':'Previously attempted; inspect receipt'},'503':{'description':'Provider/storage unavailable'}}}}
        spec['paths'][route]['post']['requestBody']={'required':True,'content':{'application/json':{'schema':published[name]}}}
    return spec


if __name__=='__main__':
    path=Path(__file__).resolve().parents[1]/'apps/web/openapi.json'
    path.write_text(json.dumps(build(json.loads(path.read_text())),indent=2)+'\n')
