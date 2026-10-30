"""Versioned, bounded editor projects; canonical physics stays in world3d."""
from copy import deepcopy
import json
from . import world3d_schema as s
from .world3d import validate_scene

REFERENCE=s.obj({'id':s.TEXT,'kind':{'enum':['video','image','telemetry','robot','legacy_2d']},
                 'sha256':{'type':'string','pattern':'^[a-f0-9]{64}$'},'source':s.TEXT,
                 'timestamp_s':s.num(0,1e12),'calibration_status':s.TEXT},['id','kind','source'])
DOCUMENT=s.obj({'schema_version':{'const':'frontiersight.editor/1.0'},'id':{'type':'string','minLength':1,'maxLength':100},
                'scene':{'oneOf':[s.SCENE,{'type':'null'}]},'media':{'type':'array','items':REFERENCE,'maxItems':64},
                'robot_models':{'type':'array','items':{'type':'object'},'maxItems':16},
                'observations':{'type':'array','items':{'type':'object'},'maxItems':64},
                'interventions':{'type':'array','items':{'type':'object'},'maxItems':64}},
               ['schema_version','id','scene','media','robot_models','observations','interventions'])
COMMAND=s.obj({'before':DOCUMENT,'after':DOCUMENT,'label':{'type':'string','maxLength':120},
               'provenance':s.TEXT,'bytes':{'type':'integer','minimum':0}},['before','after','label','provenance'])
CHECKPOINT=s.obj({'undo':{'type':'array','items':COMMAND,'maxItems':5},'redo':{'type':'array','items':COMMAND,'maxItems':5}},['undo','redo'])
PROJECT=s.obj({'schema_version':{'const':'frontiersight.project/1.0'},'document':DOCUMENT,'checkpoint':CHECKPOINT},['schema_version','document','checkpoint'])


def validate_project(value):
    value=s.validate(PROJECT,value)
    raw=json.dumps(value,allow_nan=False,separators=(',',':')).encode()
    if len(raw)>256*1024:raise ValueError('Cloud project exceeds 256 KiB; download a full recovery file instead')
    if len(json.dumps(value['checkpoint'],allow_nan=False).encode())>70000:raise ValueError('Cloud history checkpoint exceeds 70 KiB')
    pending=[value];count=0
    while pending:
        item=pending.pop();count+=1
        if count>30000:raise ValueError('Project exceeds structural budget')
        if isinstance(item,dict):
            if any(str(key).lower() in {'api_key','secret_key','operator_token','authorization','__proto__','constructor','prototype'} for key in item):
                raise ValueError('Credentials and executable keys cannot be stored in editor projects')
            pending.extend(item.values())
        elif isinstance(item,list):pending.extend(item)
    if value['document']['scene'] is None:raise ValueError('Project requires a loaded canonical scene')
    for document in [value['document']]+[entry[key] for stack in value['checkpoint'].values() for entry in stack for key in ('before','after')]:
        if document['scene'] is not None:validate_scene(document['scene'])
    for key,end in [('undo','after'),('redo','before')]:
        stack=value['checkpoint'][key]
        if stack and stack[-1][end]!=value['document']:raise ValueError('History checkpoint does not match current document')
        ordered=stack if key=='undo' else list(reversed(stack))
        for previous,current in zip(ordered,ordered[1:]):
            if previous['after']!=current['before']:raise ValueError('History checkpoint has a broken transaction chain')
    return deepcopy(value)
