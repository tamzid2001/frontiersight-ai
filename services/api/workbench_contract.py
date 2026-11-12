"""Published request schemas shared by OpenAPI and MCP; no provider secrets."""
from copy import deepcopy
from functools import lru_cache


def obj(properties, required=()):
    return {'type': 'object', 'properties': properties, 'required': list(required), 'additionalProperties': False}


def schemas(scene):
    text = {'type': 'string'}
    rid = {'type': 'string', 'format': 'uuid'}
    key = {'type': 'string', 'pattern': '^[A-Za-z0-9_-]{16,128}$'}
    number = {'type': 'number'}
    point = {'type': 'array', 'items': number, 'minItems': 2, 'maxItems': 2}
    result = {
        'plan_path': obj({'scene': scene, 'object_id': text, 'goal': point,
            'resolution_m': {'type': 'number', 'minimum': .25, 'maximum': 2, 'default': .5},
            'clearance_m': {'type': 'number', 'minimum': 0, 'maximum': 2, 'default': .1}, 'smooth': {'type': 'boolean', 'default': True}}, ('scene','object_id','goal')),
        'predict_path': obj({'points': {'type': 'array','minItems':3,'maxItems':5000,'items':{'type':'array','items':number,'minItems':3,'maxItems':3}},
            'horizon_s': {'type':'number','minimum':.1,'maximum':30,'default':3},
            'step_s': {'type':'number','minimum':.05,'maximum':5,'default':.25},
            'space':{'type':'string','enum':['world','pixel']},'stage_metres':point,'radius':{'type':'number','minimum':0,'maximum':10}}, ('points',)),
        'describe_paths': obj({'scene':scene,'description':{'type':'string','minLength':4,'maxLength':2000},'model':text},('scene','description')),
        'prepare_scene': obj({'scene':scene},('scene',)),
        'generate_scene': obj({'description':{'type':'string','minLength':1,'maxLength':4000},'model':text,
            'candidates':{'type':'integer','minimum':1,'maximum':8,'default':3}},('description',)),
        'generate_object': obj({'description':{'type':'string','minLength':1,'maxLength':300},'model':text},('description',)),
        'validate_object': obj({'spec':{'type':'object'}},('spec',)),
        'use_object': obj({'scene':scene,'object_record_id':rid,'object_id':text,'x':number,'y':number},('scene','object_record_id','object_id','x','y')),
    }
    result['render_scene_frame'] = obj({'scene':scene,'timestamp_s':{'type':'number','minimum':0,'maximum':20},
        'width':{'type':'integer','minimum':160,'maximum':1024},'height':{'type':'integer','minimum':120,'maximum':768}},('scene',))
    result['render_video_preview'] = obj({'scene':scene,'duration_s':{'type':'number','minimum':.2,'maximum':12},'fps':{'type':'integer','minimum':1,'maximum':15},
        'width':{'type':'integer','minimum':160,'maximum':1024},'height':{'type':'integer','minimum':120,'maximum':768}},('scene',))
    from engine.world3d_schema import PROFILE, SCENE
    from engine.editor_document import PROJECT
    result['propose_physics_profile']=obj({'profile':PROFILE,'description':{'type':'string','minLength':4,'maxLength':2000},'model':text},('profile','description'))
    result['get_profile']=obj({})
    result['sync_profile']=obj({})
    result['update_profile_preferences']=obj({'preferences':obj({'timezone':{'type':'string','maxLength':80},'locale':{'type':'string','maxLength':30},'reducedMotion':{'type':'boolean'}})},('preferences',))
    result['get_model_request'] = obj({'request_key':key},('request_key',))
    for kind in ('scenes','objects','media'):
        result['list_'+kind] = obj({'limit':{'type':'integer','minimum':1,'maximum':100,'default':25},'after':rid})
        result['get_'+kind] = obj({'id':rid},('id',))
        fields = {'name':{'type':'string','minLength':1,'maxLength':120}}
        required = ['name']
        if kind == 'scenes':fields['scene']={'oneOf':[scene,SCENE,PROJECT]};required.append('scene')
        elif kind == 'objects':fields['spec']={'type':'object'};required.append('spec')
        else:
            fields.update({'kind':{'type':'string','enum':['frame','video']},'data_url':{'type':'string','maxLength':180000},
                'timestamp_s':{'type':'number','minimum':0,'maximum':86400},'source_video_id':rid,'provider_file_id':{'type':'string','maxLength':160}})
            required.append('kind')
        result['create_'+kind] = obj(deepcopy(fields),required)
        result['update_'+kind] = obj({**deepcopy(fields),'id':rid,'expectedVersion':{'type':'integer','minimum':1}},required+['id','expectedVersion'])
        result['delete_'+kind] = obj({'id':rid,'expectedVersion':{'type':'integer','minimum':1}},('id','expectedVersion'))
    for kind in ('frame','video'):
        result['segment_'+kind] = obj({'media_id':rid,'concept':{'type':'string','maxLength':100}},('media_id',))
    return result

DESCRIPTIONS = {
    'get_profile':'Read only your FrontierSight-owned user profile; no Quantura profile lookup.',
    'sync_profile':'Sync your own name/email from the configured Clerk application to the FrontierSight namespace. Session-only; cannot change entitlements.',
    'update_profile_preferences':'Save only your locale, timezone and reduced-motion preferences in FrontierSight. Cannot change identity, org role or billing.',
    'propose_physics_profile':'One Muse request (20s, no retries) produces a schema-validated physics proposal. Paid authenticated workspace, model key and idempotency receipt required. Does not apply changes or authorize actuation.',
    'render_scene_frame':'Render a bounded PNG top-down simulation frame with metre-space poses, preserving the playback motion profiles. No model call; no observed-camera claim.',
    'render_video_preview':'Export a bounded animated GIF simulation preview, maximum 60 frames and 20 megapixels. This is not MP4 or photorealistic 3D video.',
    'get_model_request':'Inspect your own durable model-request status/result by the original request key. Running or failed_or_unknown never automatically retries the provider.',
    'plan_path':'Plan a bounded A* route around inflated static object footprints in metres. Moving actors are not reserved. Returns a new scene; never saves or actuates hardware.',
    'predict_path':'Fit the last 20 timestamped observations with constant velocity; return explicit future predictions and separate optional floor-constrained display points. Fit residuals are not calibrated uncertainty.',
    'describe_paths':'Request one bounded Muse path edit for existing exact object IDs. No automatic retries. Returns a new scene without saving it. Requires Researcher and an idempotency key.',
    'prepare_scene':'Build the canonical timestamped tracks, object definitions and floor dimensions for Video Studio and Counterfactuals.',
    'generate_scene':'Generate 1–8 candidates in one finite batch, select one scene, assign stable object IDs, and stop. Requires Researcher, durable storage and idempotency.',
    'generate_object':'Generate one validated buildable object recipe. No automatic repair or image-generation request. Requires Researcher and idempotency.',
    'validate_object':'Validate a custom object recipe without saving it or invoking a model.',
    'use_object':'Load an owned saved object recipe and place a uniquely named instance inside a scene. Returns a new unsaved scene.',
    'segment_frame':'Segment an owned saved JPEG/PNG frame with Meta SAM. Requires Researcher and idempotency.',
    'segment_video':'Segment a saved Meta video file reference. Video bytes remain in the provider file service. Requires Researcher and idempotency.',
}
for kind in ('scenes','objects','media'):
    for action in ('list','get','create','update','delete'):
        DESCRIPTIONS[action+'_'+kind] = f'{action.capitalize()} {kind} within the verified active Clerk workspace. ' + (
            'Mutations require Idempotency-Key; updates/deletes require expectedVersion. Organization deletion requires admin.' if action in ('create','update','delete') else 'Private data; never a public catalog.')


@lru_cache(maxsize=64)
def _validator(operation):
    import json
    from pathlib import Path
    from jsonschema import Draft202012Validator
    spec = json.loads((Path(__file__).resolve().parents[2]/'apps/web/openapi.json').read_text())
    schema = schemas({'$ref':'#/components/schemas/EditableScene'}).get(operation)
    if schema is None: raise ValueError('unknown workbench operation')
    contract = json.loads(json.dumps({'$defs':spec['components']['schemas'],**schema}).replace('#/components/schemas/','#/$defs/'))
    return Draft202012Validator(contract)


def validate_operation(operation, body):
    """Validate the published contract without resolving any external URL."""
    from jsonschema import ValidationError
    try: _validator(operation).validate(body)
    except ValidationError: raise ValueError('request does not match the published operation schema') from None
