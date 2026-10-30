import math
import pytest
from engine.observations3d import pixel_to_world, estimate_track, sam_tracks
from integrations.meta.sam import parse_output_text


def calibration():
    # Optical camera +Z points downward in ENU after a 180° rotation about X.
    return {'fx':1000,'fy':1000,'cx':320,'cy':240,'camera_pose':{'position_m':[0,0,10],'orientation_wxyz':[0,1,0,0]},
            'pixel_sigma':1,'depth_sigma_m':.01,'source':'depth_sensor','evidence_id':'camera-calibration-fixture-v1'}


def test_depth_gating_and_optical_conventions():
    assert pixel_to_world([320,240],None)['status']=='DEPTH_UNAVAILABLE'
    c=calibration();c.pop('depth_sigma_m')
    assert pixel_to_world([320,240],c)['position_m'] is None
    actual=pixel_to_world([320,240],calibration(),depth_m=5)
    assert actual['position_m']==[0,0,5] and actual['status']=='CALIBRATED_METRIC_3D'
    assert actual['uncertainty_radius_m']>0
    c=calibration();c['plane_z_m']=0
    assert pixel_to_world([420,240],c)['position_m']==[1,0,0]
    assert pixel_to_world([420,240],c)['status']=='ASSUMPTION_3D'
    c.pop('evidence_id')
    assert pixel_to_world([320,240],c,depth_m=5)['status']=='ESTIMATED_3D'


@pytest.mark.parametrize('change',[
    {'fx':0},{'plane_z_m':20},{'camera_pose':{'position_m':[0,0,0],'orientation_wxyz':[1,0,0,0]},'plane_z_m':-1},
    {'execute':'bad'}, {'camera_pose':{'position_m':[0,0,10],'orientation_wxyz':[2,0,0,0]}}
])
def test_bad_calibration(change):
    c=calibration();c.update(change)
    with pytest.raises(ValueError): pixel_to_world([320,240],c,depth_m=None)


def test_variable_timestamps_occlusion_and_identity():
    points=[{'t_s':0,'position':[0,0]},{'t_s':.1,'position':[.1,0]}, {'t_s':.4,'position':[.4,0]},
            {'t_s':2,'position':[2,0]}, {'t_s':2.1,'position':[9,0],'identity_continuous':False}]
    r=estimate_track(points,alpha=1,beta=1)
    assert r['observations'][1]['velocity']==pytest.approx([1,0,0])
    assert r['observations'][2]['velocity']==pytest.approx([1,0,0])
    assert r['observations'][3]['diagnostic']=='occlusion_reset'
    assert not r['observations'][3]['velocity_available']
    assert r['observations'][4]['diagnostic']=='identity_reset'
    assert r['motion_interpretation']=='apparent_motion_camera_motion_unresolved'
    assert estimate_track(points,camera_stabilized=True)['motion_interpretation']=='world_motion_estimate'


@pytest.mark.parametrize('points',[
    [],[{'t_s':0,'position':[0,0]}]*2,
    [{'t_s':1,'position':[0,0]},{'t_s':0,'position':[1,0]}],
    [{'t_s':0,'position':[0,0]},{'t_s':1,'position':[1,0,0]}],
    [{'t_s':0,'position':[0,0]},{'t_s':1,'position':[float('nan'),0]}],
    [{'t_s':0,'position':[0,0]},{'t_s':1,'position':[1,0],'confidence':2}],
    [{'t_s':0,'position':[0,0]},{'t_s':1,'position':[1,0],'identity_continuous':'yes'}],
])
def test_invalid_observations(points):
    with pytest.raises(ValueError): estimate_track(points)


def test_real_sam_format_and_source_pts():
    text='<0f>7<|box;x1=0;y1=0;x2=10;y2=10;w=100;h=100;c=0.9|>\n<2f>7<|box;x1=4;y1=0;x2=14;y2=10;w=100;h=100;c=0.7|>'
    parsed=parse_output_text(text);result=sam_tracks(parsed,[0,.07,.21])
    assert result['tracks'][0]['points'][1]['t_s']==.21
    assert result['tracks'][0]['points'][1]['confidence']==.7
    assert result['space']=='pixel' and not result['depth_available']
    assert sam_tracks(parsed,[0,.07,.21],reference='bottom_center')['tracks'][0]['points'][0]['position']==[5,10]
    with pytest.raises(ValueError):sam_tracks(parsed,[0,.07,.21],reference='mask_centroid')
    with pytest.raises(ValueError):sam_tracks(parsed,[0,.07])
    with pytest.raises(ValueError):sam_tracks(parsed,[0,.2,.1])
