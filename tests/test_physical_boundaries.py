from copy import deepcopy
import math
import pytest
from engine.demos3d import warehouse,flying,base,body,profile,upgrade_2d,demonstration
from engine.world3d import validate_scene,simulate,compare,validate_profile,_finite_tree
from engine.trajectory3d import at,validate
from engine.spatial3d import Vector3 as V,Quaternion as Q,Pose3D,finite,segment_distance
from engine.geometry3d import separation,sweep,radius,extent
from edge.safety import validate_recommendation


def test_c2_timed_xyz_and_analytical_limits():
    points=[{'t_s':0,'position_m':[0,0,1]},{'t_s':4,'position_m':[2,0,3]}]
    p=profile('constant_acceleration')
    validate(points,p,[0,0,1])
    assert at(points,0)==(V(0,0,1),V(),V())
    assert at(points,2)[0]==V(1,0,2)
    assert at(points,4)==(V(2,0,3),V(),V())
    scene=base('3D waypoint path',[body('drone',[0,0,1],[.1,.1,.1],'constant_acceleration',waypoints=points)],5)
    result=simulate(scene)
    assert result['frames'][-1]['objects'][0]['position_m']==[2,0,3]
    for mutated in ([points[0],{'t_s':0,'position_m':[2,0,3]}], [{'t_s':1,'position_m':[0,0,1]},points[1]],points[:1]):
        with pytest.raises(ValueError):validate(mutated,p,[0,0,1])
    with pytest.raises(ValueError):validate(points,p,[0,0,1],ground=True)
    for key in ('max_horizontal_speed_mps','max_vertical_speed_mps','max_acceleration_mps2'):
        restricted={**p,key:.001}
        with pytest.raises(ValueError):validate(points,restricted,[0,0,1])


def test_waypoint_constraints_and_load_capacity():
    scene=warehouse();scene['objects'][3]['physics']['mass_kg']=1300
    assert any(x['code']=='payload_capacity' for x in simulate(scene)['constraints'])
    mutations=[
        lambda s:s['objects'][0].update(velocity_mps=[1,0,0]),
        lambda s:s['objects'][0]['physics'].update(motion_model='static'),
        lambda s:s['objects'][2]['joint'].update(speed_mps=9),
        lambda s:s['objects'][2].pop('joint'),
        lambda s:s['objects'][1].pop('attachment'),
        lambda s:s['objects'][0].update(angular_velocity_radps=[0,0,1]),
        lambda s:s['objects'][0].update(angular_velocity_radps=[0,0,3]),
        lambda s:s['objects'][3].update(provenance='HARDWARE_OBSERVATION'),
    ]
    for change in mutations:
        candidate=warehouse();change(candidate)
        with pytest.raises(ValueError):validate_scene(candidate)
    sphere=body('s',[0,0,1],[.1,.1,.1],'ground_air_hybrid',physics=profile('ground_air_hybrid',hypothetical=True),velocity_mps=[0,0,-1])
    assert simulate(base('ground contact',[sphere],1))['frames'][-1]['objects'][0]['position_m'][2]==pytest.approx(.1)
    with pytest.raises(ValueError):validate_profile(profile('ground_air_hybrid',hypothetical=True,mass_kg=.001,thrust_n=[1e8,0,0]))


def test_rotation_drag_saturated_speed_and_geometry_bounds():
    scene=base('rotation',[body('r',[0,0,1],[1,.1,.1],'constant_acceleration',angular_velocity_radps=[0,0,1],velocity_mps=[1,0,0],physics=profile('constant_acceleration',linear_drag_per_s=.1))],1)
    end=simulate(scene)['frames'][-1]['objects'][0]
    assert end['orientation_wxyz'][3]>0 and end['velocity_mps'][0]<1
    scene['objects'][0]['acceleration_mps2']=[100,0,0]
    scene['objects'][0]['physics']['max_acceleration_mps2']=100
    scene['objects'][0]['physics']['linear_drag_per_s']=10
    scene['objects'][0]['velocity_mps']=[-1,0,0]
    with pytest.raises(ValueError):simulate(scene)
    box={'kind':'box','half_extents_m':[1,2,3]}
    assert radius(box)==pytest.approx(math.sqrt(14))
    assert extent(box,Pose3D()).array()==[1,2,3]
    sphere={'kind':'sphere','radius_m':1}
    assert extent(sphere,Pose3D())==V(1,1,1)
    assert sweep(sphere,Pose3D(),Pose3D(),sphere,Pose3D(V(5,0,0)),Pose3D(V(5,0,0)))[0] is None
    assert separation(box,Pose3D(),sphere,Pose3D())[1]
    cap={'kind':'capsule','radius_m':1,'half_length_m':2}
    assert radius(cap)==3
    assert separation(sphere,Pose3D(),cap,Pose3D())[1]
    assert segment_distance(V(),V(1,0,0),V(2,1,0),V(2,2,0))==pytest.approx(math.sqrt(2))


def test_legacy_scene_conversion_and_explicit_failures():
    legacy={'stage_metres':[16,14],'objects':[{'id':'robot-1','category':'robot','waypoints':[[2,3],[4,3]],'speed':1,'radius':.4}]}
    converted=upgrade_2d(legacy)
    assert converted['objects'][0]['pose']['position_m']==[2,3,.4]
    assert converted['objects'][0]['velocity_mps']==[1,0,0]
    assert legacy['objects'][0]['waypoints']==[[2,3],[4,3]]
    with pytest.raises(ValueError):upgrade_2d({'stage_metres':[16,14],'objects':[]})
    with pytest.raises(ValueError):demonstration('unknown')
    for value in (True,'1',float('inf'),10**1000):
        with pytest.raises(ValueError):finite(value)
    with pytest.raises(ValueError):Q.read([1,0,0])
    _finite_tree({'nested':[1,2,3]})
    with pytest.raises(ValueError):compare(warehouse(),[{'object_id':'chassis'},{'object_id':'chassis'}])


def test_advisory_supervisor_never_actuates_and_checks_freshness():
    recommendation={'object_id':'robot','velocity_mps':[.3,0,0],'expires_at_s':10.5}
    health={'mode':'ADVISORY','connected':True,'observed_at_s':9.8,'independent_interlock_ok':True}
    result=validate_recommendation(recommendation,health,now_s=10)
    assert result['accepted'] and not result['actuation']
    for override in ({'mode':'SHADOW'},{'mode':'CONTROLLED_BENCH'},{'connected':False},{'observed_at_s':1},{'independent_interlock_ok':False}):
        assert not validate_recommendation(recommendation,{**health,**override},now_s=10)['accepted']
    assert not validate_recommendation({**recommendation,'expires_at_s':20},health,now_s=10)['accepted']
    assert not validate_recommendation({**recommendation,'velocity_mps':[10,0,0]},health,now_s=10)['accepted']
    with pytest.raises(ValueError):validate_recommendation({'command':'disable_estop'},health,now_s=10)


def test_exact_3d_closest_approach_and_ttc():
    from engine.geometry3d import closest_approach
    r=closest_approach([0,0,0],[1,0,0],.5,[10,0,0],[-1,0,0],.5,10)
    assert r['time_to_contact_s']==pytest.approx(4.5) and r['closest_approach_s']==5
    assert closest_approach([0,0,12],[1,0,0],.5,[5,0,0],[0,0,0],.5,10)['time_to_contact_s'] is None
    assert closest_approach([0,0,0],[0,0,0],.5,[5,0,0],[0,0,0],.5,10)['clearance_m']==4
    assert closest_approach([0,0,0],[-1,0,0],.5,[5,0,0],[1,0,0],.5,10)['closest_approach_s']==0
