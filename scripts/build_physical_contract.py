"""Regenerate v2 and additive v1 contracts from canonical Python schemas."""
import json
from copy import deepcopy
from pathlib import Path
from services.api.physical import ROUTES, SCHEMAS, DESCRIPTIONS, OUTPUT_SCHEMAS
from services.api.workbench_http import ROUTES as WORKBENCH_ROUTES
from services.api.workbench_contract import schemas,DESCRIPTIONS as WORKBENCH_DESCRIPTIONS
from engine.world3d_schema import SCENE,PROFILE,RESULT,FRAME,CALIBRATION


def build(spec):
    spec['info']['version']='0.39.0'
    spec['components']['securitySchemes']['FrontierAgentKey']={'type':'http','scheme':'bearer','bearerFormat':'fsa_ personal key','description':'Scoped FrontierSight personal key. Read/write/model scopes, expiry and revocation are enforced server-side; session-only operations reject keys.'}
    spec['components']['schemas'].update(Scene3D=SCENE,PhysicsProfile3D=PROFILE,WorldState3D=FRAME,Calibration3D=CALIBRATION)
    result_schema=deepcopy(RESULT)
    result_schema['properties']['scene']={'$ref':'#/components/schemas/Scene3D'}
    result_schema['properties']['calibration']={'$ref':'#/components/schemas/Calibration3D'}
    result_schema['properties']['frames']['items']={'$ref':'#/components/schemas/WorldState3D'}
    spec['components']['schemas']['SimulationResult3D']=result_schema
    comparison=deepcopy(OUTPUT_SCHEMAS['simulate_counterfactual_3d'])
    for key in ('baseline','counterfactual'):comparison['properties'][key]={'$ref':'#/components/schemas/SimulationResult3D'}
    spec['components']['schemas']['SimulationComparison3D']=comparison
    response_schemas={'simulate_scene_3d':{'$ref':'#/components/schemas/SimulationResult3D'},'simulate_counterfactual_3d':{'$ref':'#/components/schemas/SimulationComparison3D'}}
    for route,name in ROUTES.items():
        spec['paths'][route]={'post':{'operationId':name,'summary':DESCRIPTIONS[name],
            'requestBody':{'required':True,'content':{'application/json':{'schema':SCHEMAS[name]}}},
            'responses':{'200':{'description':'Deterministic result with explicit provenance and numerical methods','content':{'application/json':{'schema':response_schemas.get(name,{'type':'object'})}}},
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
                'security':[{'ClerkSession':[]}],'parameters':[{'in':'header','name':'Idempotency-Key','schema':{'type':'string'},'required':True}],
                'responses':{'200':{'description':'Validated proposal, no scene mutation'},'400':{'description':'Invalid request'},'401':{'description':'Authentication required'},
                             '402':{'description':'Researcher plan required'},'409':{'description':'Previously attempted; inspect receipt'},'503':{'description':'Provider/storage unavailable'}}}}
        spec['paths'][route]['post']['security']=([{'ClerkSession':[]}] if name=='sync_profile' else [{'ClerkSession':[]},{'FrontierAgentKey':[]}])
        spec['paths'][route]['post']['requestBody']={'required':True,'content':{'application/json':{'schema':published[name]}}}
    return spec


if __name__=='__main__':
    path=Path(__file__).resolve().parents[1]/'apps/web/openapi.json'
    path.write_text(json.dumps(build(json.loads(path.read_text())),indent=2)+'\n')
