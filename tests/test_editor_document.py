from copy import deepcopy
import pytest
from engine.demos3d import warehouse
from engine.editor_document import validate_project


def project():
    document={'schema_version':'frontiersight.editor/1.0','id':'fixture','scene':warehouse(),'media':[],'robot_models':[],'observations':[],'interventions':[]}
    return {'schema_version':'frontiersight.project/1.0','document':document,'checkpoint':{'undo':[],'redo':[]}}


def test_project_scene_and_history_validation():
    value=project();before=deepcopy(value['document']);value['document']['scene']['name']='Edited warehouse'
    value['checkpoint']['undo']=[{'before':before,'after':deepcopy(value['document']),'label':'Rename','provenance':'ASSUMPTION'}]
    assert validate_project(value)==value
    bad=deepcopy(value);bad['checkpoint']['undo'][-1]['after']=before
    with pytest.raises(ValueError,match='does not match'):validate_project(bad)
    bad=deepcopy(value);bad['document']['scene']['objects'][0]['physics']['mass_kg']=-1
    with pytest.raises(ValueError):validate_project(bad)
    bad=project();bad['document']['robot_models']=[{'operator_token':'private'}]
    with pytest.raises(ValueError,match='Credentials'):validate_project(bad)
    bad=project();bad['document']['observations']=[{'text':'x'*300000}]
    with pytest.raises(ValueError,match='256 KiB'):validate_project(bad)


def test_project_firestore_roundtrip_and_tenant_boundaries():
    import os,uuid
    if not os.environ.get('FIRESTORE_EMULATOR_HOST'):pytest.skip('Firestore emulator required')
    from services.api.firestore_scenes import client,Scenes
    from services.api.clerk_auth import Identity,WorkspaceError
    database=client({'FIRESTORE_PROJECT_ID':'demo-quantura-web','FIRESTORE_EMULATOR_HOST':os.environ['FIRESTORE_EMULATOR_HOST']})
    identity=Identity('user_project_'+uuid.uuid4().hex,None,None,'researcher')
    library=Scenes(database,identity,'fixture-audit-secret-with-sufficient-length')
    from services.api.workbench import Workbench
    service=Workbench(identity,stores={'scenes':library})
    value=validate_project(project());response=service.execute('create_scenes',{'name':'Editor','scene':value},'fixture-'+uuid.uuid4().hex)
    assert library.get(response['id'])['payload']==value
    with pytest.raises(WorkspaceError):Scenes(database,Identity('user_other',None,None,'researcher'),'fixture-audit-secret-with-sufficient-length').get(response['id'])
    database.close()


def test_checkpoint_chains_and_resource_budgets():
    first=project();a=deepcopy(first['document']);b=deepcopy(a);b['scene']['name']='B';c=deepcopy(b);c['scene']['name']='C'
    first['document']=c;first['checkpoint']['undo']=[{'before':a,'after':b,'label':'A-B','provenance':'ASSUMPTION'},{'before':b,'after':c,'label':'B-C','provenance':'ASSUMPTION'}]
    assert validate_project(first)==first
    first['checkpoint']['undo'][0]['after']=a
    with pytest.raises(ValueError,match='broken transaction'):validate_project(first)
    many=project();many['document']['observations']=[{'items':list(range(600))} for _ in range(55)]
    with pytest.raises(ValueError,match='structural'):validate_project(many)
    large=project();large['document']['observations']=[{'text':'x'*70000}];large['checkpoint']['undo']=[{'before':deepcopy(large['document']),'after':deepcopy(large['document']),'label':'large','provenance':'ASSUMPTION'}]
    with pytest.raises(ValueError,match='70 KiB'):validate_project(large)
