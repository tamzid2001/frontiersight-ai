import copy
import math
import pytest
from engine.spatial3d import Vector3 as V, Quaternion as Q, Pose3D, segment_distance
from engine.geometry3d import separation, sweep
from engine.world3d import validate_scene, validate_profile, simulate, compare, joint_at
from engine.demos3d import body, base, profile, warehouse, flying


def test_spatial_transform_and_rotation():
    q=Q(math.cos(math.pi/4),0,0,math.sin(math.pi/4))
    p=Pose3D(V(1,0,0),q).compose(Pose3D(V(1,0,0)))
    assert p.position.x==pytest.approx(1)
    assert p.position.y==pytest.approx(1)
    assert q.inverse().rotate(q.rotate(V(1,2,3))).array()==pytest.approx([1,2,3])
    assert Q().advance(V(0,0,1),math.pi).rotate(V(1,0,0)).x==pytest.approx(-1)
    assert segment_distance(V(),V(),V(1,0,0),V(2,0,0))==1
    assert segment_distance(V(),V(1,0,0),V(0,1,0),V(1,1,0))==1
    assert segment_distance(V(),V(1,0,0),V(),V())==0
    with pytest.raises(ValueError): Q(1,1,0,0)
    with pytest.raises(ValueError): V.read([1,2])
    with pytest.raises(ValueError): V(float('nan'),0,0)


def test_constant_velocity_acceleration_and_gravity():
    scene=base('Analytic',[body('a',[0,0,10],[.1,.1,.1],'constant_acceleration',velocity_mps=[1,2,3],acceleration_mps2=[2,0,-1],physics=profile('constant_acceleration',max_horizontal_speed_mps=10))],2)
    result=simulate(scene);end=result['frames'][-1]['objects'][0]
    assert end['position_m']==pytest.approx([6,4,14])
    assert end['velocity_mps']==pytest.approx([5,2,1])
    scene['objects'][0].update(velocity_mps=[0,0,0],acceleration_mps2=[0,0,0],physics=profile('ballistic',max_vertical_speed_mps=100))
    assert simulate(scene)['frames'][-1]['objects'][0]['position_m'][2]==pytest.approx(10-.5*9.80665*4)
    assert result==simulate(base('Analytic',[body('a',[0,0,10],[.1,.1,.1],'constant_acceleration',velocity_mps=[1,2,3],acceleration_mps2=[2,0,-1],physics=profile('constant_acceleration',max_horizontal_speed_mps=10))],2))


def test_different_elevations_and_swept_collision():
    scene=base('Crossing',[body('a',[-1,0,12],[.1,.1,.1],'constant_acceleration',velocity_mps=[5,0,0]),body('b',[0,0,.1],[.1,.1,.1])],.5)
    scene['step_s']=.25
    assert simulate(scene)['events']==[]
    scene['objects'][0]['pose']['position_m'][2]=.1
    contacts=simulate(scene)['events']
    assert any(e['kind']=='CONTACT' and e['method']=='exact_linear_aabb' for e in contacts)
    assert contacts[0]['t_s']==pytest.approx(.16)
    sphere={'kind':'sphere','radius_m':.1}
    t,method=sweep(sphere,Pose3D(V(-1,0,0)),Pose3D(V(1,0,0)),sphere,Pose3D(),Pose3D())
    assert t==pytest.approx(.4) and method=='exact_linear_sphere'


def test_boxes_spheres_capsules_and_orientation():
    box={'kind':'box','half_extents_m':[1,.1,.1]};sphere={'kind':'sphere','radius_m':.2}
    assert separation(sphere,Pose3D(V(0,0,2)),box,Pose3D())[0]==pytest.approx(1.7)
    q=Q(math.cos(math.pi/4),0,0,math.sin(math.pi/4))
    gap,contact,method=separation(box,Pose3D(),box,Pose3D(V(0,1,0),q))
    assert contact and method.startswith('obb_sat')
    capsule={'kind':'capsule','radius_m':.1,'half_length_m':1.}
    assert separation(capsule,Pose3D(),capsule,Pose3D(V(1,0,0)))[0]==pytest.approx(.8)
    assert separation(capsule,Pose3D(),box,Pose3D())[2]=='enclosing_aabb_lower_bound'


def test_articulated_forks_remain_independent():
    scene=warehouse();result=simulate(scene)
    first={o['id']:o for o in result['frames'][0]['objects']}
    last={o['id']:o for o in result['frames'][-1]['objects']}
    assert first['chassis']['position_m'][2]==last['chassis']['position_m'][2]==.65
    assert last['chassis']['position_m'][0]==4
    assert last['forks']['position_m'][2]-first['forks']['position_m'][2]==pytest.approx(2.6)
    assert last['payload']['position_m'][2]-last['forks']['position_m'][2]==pytest.approx(.36)
    changed=copy.deepcopy(scene['objects'][2]['joint']);changed['target_m']=3.5
    report=compare(scene,[{'object_id':'forks','joint':changed}])
    assert report['baseline']['source_digest']!=report['counterfactual']['source_digest']
    assert any(e['objects']==['payload','overhead-beam'] and e['kind']=='CONTACT' for e in report['counterfactual']['events'])
    assert scene['objects'][2]['joint']['target_m']==2.6


def test_joint_rest_to_rest_and_descending():
    joint=warehouse()['objects'][2]['joint'];joint['start_s']=1.
    assert joint_at(joint,0)==(0,0,0)
    assert joint_at(joint,1.2)[1]==pytest.approx(.1)
    assert joint_at(joint,20)==(2.6,0,0)
    joint.update(initial_m=2.6,target_m=0)
    assert joint_at(joint,2)[1]<0
    assert joint_at(joint,20)==(0,0,0)
    joint.update(target_m=2.59)
    assert joint_at(joint,1.01)[2]<0


def test_flying_counterfactual_and_limits():
    scene=flying();result=simulate(scene)
    assert result['frames'][-1]['objects'][0]['position_m'][2]>12
    assert not any(e['kind']=='CONTACT' and e['objects']==['flying-vehicle','ground-person'] for e in result['events'])
    assert any(e['code']=='speed_limit' for e in result['constraints'])
    report=compare(scene,[{'object_id':'flying-vehicle','acceleration_mps2':[0,0,0]}])
    assert any(e['kind']=='CONTACT' for e in report['counterfactual']['events'])
    scene=warehouse();scene['objects'][0].pop('waypoints');scene['objects'][0]['velocity_mps']=[.4,0,0]
    assert any(e['code']=='elevated_load_speed' for e in simulate(scene)['constraints'])


@pytest.mark.parametrize('mutate',[
    lambda s:s.update(schema_version='3.0'),
    lambda s:s.update(step_s=float('nan')),
    lambda s:s.update(duration_s=30,step_s=.01),
    lambda s:s['objects'].append(copy.deepcopy(s['objects'][0])),
    lambda s:s['objects'][0]['pose'].update(orientation_wxyz=[2,0,0,0]),
    lambda s:s['objects'][0]['physics'].update(mass_kg=-1),
    lambda s:s['objects'][0].update(velocity_mps=[100,0,0]),
    lambda s:s['objects'][0]['pose'].update(position_m=[4,4,1]),
    lambda s:s['objects'][0]['physics'].update(motion_model='execute_python'),
    lambda s:s['objects'][2].update(parent_id='missing'),
    lambda s:s['objects'][2]['joint'].update(target_m=10),
    lambda s:s['objects'][2].update(velocity_mps=[0,0,1]),
    lambda s:s['calibration'].update(status='CALIBRATED_METRIC_3D'),
    lambda s:s['calibration'].update(status='ESTIMATED_3D'),
    lambda s:s.update(excluded_pairs=[['chassis','unknown']]),
])
def test_invalid_states_rejected(mutate):
    scene=warehouse();mutate(scene)
    with pytest.raises(ValueError): validate_scene(scene)


def test_invalid_intervention_and_profile():
    with pytest.raises(ValueError): compare(warehouse(),[{'object_id':'chassis','eval':'bad'}])
    with pytest.raises(ValueError): compare(warehouse(),[{'object_id':'unknown'}])
    with pytest.raises(ValueError): compare(warehouse(),[])
    with pytest.raises(ValueError): validate_profile(profile('ground_air_hybrid'))
