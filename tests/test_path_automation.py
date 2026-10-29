import copy
import math
import pytest
from engine.path_automation import plan_object_path, predict_track, segment_clear


def scene(obstacles=True):
    objects=[{'id':'robot-1','category':'robot','speed':1.,'radius':.5,'waypoints':[[2.,7.]],'custom':{'tag':'preserve'}}]
    if obstacles:objects.append({'id':'shelf-1','category':'shelf','speed':0.,'radius':2.,'waypoints':[[8.,7.]]})
    return {'stage_metres':[16.,14.],'name':'Planner test','objects':objects}


def test_planner_routes_around_inflated_static_obstacles_without_mutating_scene():
    original=scene();snapshot=copy.deepcopy(original)
    result=plan_object_path(original,'robot-1',[14,7],smooth=False)
    obj=result['scene']['objects'][0]
    assert obj['waypoints'][0]==[2,7] and obj['waypoints'][-1]==[14,7]
    assert len(obj['waypoints'])>=3 and obj['radius']==.5 and obj['custom']=={'tag':'preserve'}
    assert all(segment_clear(a,b,[(8,7,2.6)]) for a,b in zip(obj['waypoints'],obj['waypoints'][1:]))
    assert original==snapshot and result['expansions']>0


def test_clear_route_and_stationary_goal_need_no_search():
    assert plan_object_path(scene(False),'robot-1',[14,7])['scene']['objects'][0]['waypoints']==[[2,7],[14,7]]
    same=plan_object_path(scene(False),'robot-1',[2,7])
    assert same['scene']['objects'][0]['waypoints']==[[2,7]] and same['expansions']==0


def test_smooth_curve_is_verified_against_the_same_engine_geometry():
    result=plan_object_path(scene(),'robot-1',[14,7],smooth=True)
    obj=result['scene']['objects'][0]
    from engine.curves import Path
    pts=Path(obj['waypoints'],obj['curve'],False).points
    assert all(segment_clear([a.x,a.y],[b.x,b.y],[(8,7,2.6)]) for a,b in zip(pts,pts[1:]))


@pytest.mark.parametrize('patch',[
    {'object_id':'missing'}, {'goal':[0,7]}, {'goal':[8,7]}, {'resolution_m':.01},
    {'clearance_m':-1}, {'maximum_expansions':0}, {'maximum_expansions':True},
    {'smooth':'yes'}, {'goal':[math.nan,2]}, {'goal':[2]},
])
def test_invalid_planner_requests_fail_before_any_mutation(patch):
    original=scene();snapshot=copy.deepcopy(original);args={'object_id':'robot-1','goal':[14,7],**patch}
    with pytest.raises(ValueError):plan_object_path(original,**args)
    assert original==snapshot


def test_planning_budget_and_blocked_goals_are_explicit_failures():
    with pytest.raises(ValueError,match='expansion budget'):plan_object_path(scene(),'robot-1',[14,7],maximum_expansions=1)
    blocked=scene();blocked['objects'][0]['speed']=0
    with pytest.raises(ValueError,match='positive speed'):plan_object_path(blocked,'robot-1',[14,7])
    blocked['objects'][0]['speed']=1;blocked['objects'][0]['waypoints']=[]
    with pytest.raises(ValueError,match='place the object'):plan_object_path(blocked,'robot-1',[14,7])


def test_moving_other_actors_are_not_misrepresented_as_reserved_trajectories():
    original=scene(False);original['objects'].append({'id':'actor-2','category':'pedestrian','speed':1,'radius':.5,'waypoints':[[4,2],[4,12]]})
    result=plan_object_path(original,'robot-1',[14,7])
    assert result['unreserved_moving_actors']==1 and result['static_obstacles']==0
    assert 'physical safety' in result['warnings'][-1]


def test_prediction_recovers_velocity_with_nonuniform_absolute_times():
    base=1793300000.;times=[0,.1,.4,1.,2.]
    points=[[base+t,2+1.5*t,4-.25*t] for t in times]
    p=predict_track(points,horizon_s=2,step_s=.3)
    assert p['velocity']==pytest.approx([1.5,-.25],abs=1e-6)
    assert p['points'][0]==points[-1]
    assert p['points'][-1]==pytest.approx([base+4,8,3],abs=1e-6)
    assert p['fit_rmse']<1e-6 and p['source']=='PREDICTED'


def test_prediction_uses_only_recent_observations_and_does_not_jump_to_fitted_intercept():
    points=[[t,t+(1 if t==29 else 0),2] for t in range(30)]
    p=predict_track(points)
    assert p['fit_observations']==20 and p['points'][0]==points[-1]
    assert p['input_cutoff']==29 and p['fit_rmse']>0


def test_boundary_hold_is_separate_from_the_unconstrained_prediction():
    p=predict_track([[0,12,7],[1,13,7],[2,14,7]],horizon_s=4,stage_metres=[16,14],radius=.5)
    assert p['points'][-1][1]==18
    assert p['staged_points'][-1][1]==15.5
    assert p['boundary_hold_after_s']==1.5
    assert p['staged_points'][0]==[2,14,7]


@pytest.mark.parametrize('points,extra',[
    ([[0,1,1],[0,2,2],[1,3,3]],{}), ([[0,1,1],[1,2,2]],{}),
    ([[0,1,1],[1,math.inf,2],[2,3,3]],{}), ([[0,1],[1,2],[2,3]],{}),
    ([[0,1,1],[.001,2,2],[.002,3,3]],{}),
    ([[0,1,1],[1,500,2],[2,1000,3]],{}),
    ([[0,1,1],[1,2,2],[2,3,3]],{'horizon_s':30,'step_s':.05}),
    ([[0,1,1],[1,2,2],[2,3,3]],{'space':'pixel','stage_metres':[16,14]}),
    ([[0,1,1],[1,2,2],[2,3,3]],{'space':'invalid'}),
    ([[0,1,1],[1,2,2],[2,30,3]],{'stage_metres':[16,14]}),
])
def test_invalid_observations_and_overlarge_work_are_rejected(points,extra):
    with pytest.raises(ValueError):predict_track(points,**extra)


def test_stationary_pixel_prediction_does_not_invent_metric_calibration():
    p=predict_track([[0,4,5],[1,4,5],[2,4,5]],space='pixel')
    assert p['space']=='pixel' and p['staged_points'] is None and p['velocity']==[0,0]
