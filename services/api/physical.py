"""One deterministic dispatcher shared by HTTP, MCP and offline edge replay."""
from copy import deepcopy
from engine import world3d, world3d_schema as s
from engine.demos3d import demonstration, upgrade_2d
from engine.observations3d import estimate_track, pixel_to_world, sam_tracks, assumption_scene

CHANGE=s.obj({'object_id':s.IDENTITY,'physics':s.PROFILE,'joint':s.JOINT,'pose':s.POSE,
              'velocity_mps':s.vec(-200,200),'acceleration_mps2':s.vec(-100,100),'waypoints':s.BODY['properties']['waypoints'],'geometry':s.GEOMETRY,'angular_velocity_radps':s.vec(-20,20)},['object_id'])
SCHEMAS={
    'compare_scene_documents_3d':s.obj({'baseline':s.SCENE,'alternative':s.SCENE},['baseline','alternative']),
    'closest_approach_3d':s.obj({'position_a':s.vec(),'velocity_a':s.vec(-200,200),'radius_a':s.num(0,100),'position_b':s.vec(),'velocity_b':s.vec(-200,200),'radius_b':s.num(0,100),'horizon_s':s.num(.001,30)},['position_a','velocity_a','radius_a','position_b','velocity_b','radius_b','horizon_s']),
    'tracks_to_assumed_scene_3d':s.obj({'tracks':{'type':'array','items':{'type':'object'},'minItems':1,'maxItems':16},'metres_per_pixel':s.num(.000001,100),'height_m':s.num(0,100),'radius_m':s.num(.001,20)},['tracks','metres_per_pixel']),
    'get_scene_3d':s.obj({'demo':{'enum':['warehouse','flying']}},['demo']),
    'prepare_scene_3d':s.obj({'scene':s.SCENE},['scene']),
    'validate_physics_profile':s.obj({'profile':s.PROFILE},['profile']),
    'simulate_scene_3d':s.obj({'scene':s.SCENE},['scene']),
    'simulate_counterfactual_3d':s.obj({'scene':s.SCENE,'changes':{'type':'array','items':CHANGE,'minItems':1,'maxItems':16}},['scene','changes']),
    'upgrade_planar_scene':s.obj({'scene':{'type':'object'}},['scene']),
    'estimate_kinematics_3d':s.obj({'points':{'type':'array','items':{'type':'object'},'minItems':2,'maxItems':5000},
                                  'alpha':s.num(.001,1),'beta':s.num(0,1),'max_gap_s':s.num(.001,60),
                                  'observation_sigma':s.num(.000001,1000),'camera_stabilized':{'type':'boolean'}},['points']),
    'calibrate_scene':s.obj({'pixel':{'type':'array','items':s.num(0,16384),'minItems':2,'maxItems':2},
                           'calibration':{'type':['object','null']},'depth_m':s.num(.001,10000)},['pixel']),
    'extract_video_tracks':s.obj({'segmentation':{'type':'object'},'frame_timestamps_s':{'type':'array','items':s.num(0,1e9),'maxItems':100000},
                                'reference':{'enum':['box_center','bottom_center','mask_centroid']},'camera_stabilized':{'type':'boolean'}},['segmentation','frame_timestamps_s']),
    'export_evidence_packet_3d':s.obj({'scene':s.SCENE},['scene']),
}
DESCRIPTIONS={
    'compare_scene_documents_3d':'Recompute complete baseline and alternative canonical scenes, including structural edits; source hashes and changed identities retained. Simulation only.',
    'closest_approach_3d':'Exact sphere separation, closest approach and time-to-contact under declared constant 3D velocities and horizon. No measured-depth claim.',
    'tracks_to_assumed_scene_3d':'Convert pixel tracks using explicit user scale, constant height and sphere-radius assumptions. Never claims measured depth; use aligned track timestamps.',
    'get_scene_3d':'Get a synthetic warehouse or hypothetical flight scene in canonical SI/ENU format; no hardware observation.',
    'prepare_scene_3d':'Validate and hash a versioned SI/ENU scene, ordered articulated hierarchy and bounded compute requirements.',
    'validate_physics_profile':'Reject unsupported motion models, invalid units/ranges and undeclared hypothetical flight. No code execution.',
    'simulate_scene_3d':'Deterministic 3D kinematic prediction with articulated forks, geometric contact/possible-contact distinction and declared constraints. No contact response or actuation.',
    'simulate_counterfactual_3d':'Compute baseline and edited 3D simulations from typed interventions. Conditional comparison, not causal proof.',
    'upgrade_planar_scene':'Preserve the original 2D document and create an explicitly assumption-based initial-state 3D prediction. Curved paths stay in the 2D workflow.',
    'estimate_kinematics_3d':'Variable-dt alpha-beta apparent-motion estimates with occlusion resets and declared error; accepts 2D/3D positions without fabricating depth.',
    'calibrate_scene':'Apply declared pinhole intrinsics and camera-to-ENU pose to supplied optical depth or an assumption-based horizontal plane. No monocular depth inference.',
    'extract_video_tracks':'Join within-response SAM IDs to actual source-frame PTS, retain confidence and estimate pixel-space motion. No cross-response identity guarantee.',
    'export_evidence_packet_3d':'Export hash-bound scene, simulation and interpretation; hashes provide integrity, not measurement authenticity or a safety certificate.',
}
ROUTES={
    '/api/v2/counterfactuals/scenes':'compare_scene_documents_3d',
    '/api/v2/geometry/closest-approach':'closest_approach_3d',
    '/api/v2/tracks/assumed-scene':'tracks_to_assumed_scene_3d',
    '/api/v2/scenes/demo':'get_scene_3d','/api/v2/scenes/prepare':'prepare_scene_3d',
    '/api/v2/physics/validate':'validate_physics_profile','/api/v2/simulations/run':'simulate_scene_3d',
    '/api/v2/counterfactuals/compare':'simulate_counterfactual_3d','/api/v2/scenes/upgrade':'upgrade_planar_scene',
    '/api/v2/tracks/estimate':'estimate_kinematics_3d','/api/v2/calibration/project':'calibrate_scene',
    '/api/v2/tracks/extract':'extract_video_tracks','/api/v2/evidence/export':'export_evidence_packet_3d',
}


OUTPUT_SCHEMAS={'simulate_scene_3d':s.RESULT,'simulate_counterfactual_3d':s.obj({'schema_version':{'const':'2.0'},'baseline':s.RESULT,'counterfactual':s.RESULT,'changes':{'type':'array','items':CHANGE,'minItems':1,'maxItems':16},'interpretation':s.TEXT},['schema_version','baseline','counterfactual','changes','interpretation'])}


OUTPUT_SCHEMAS['compare_scene_documents_3d']=s.obj({'schema_version':{'const':'2.0'},'baseline':s.RESULT,'counterfactual':s.RESULT,
    'baseline_digest':{'type':'string','pattern':'^[a-f0-9]{64}$'},'alternative_digest':{'type':'string','pattern':'^[a-f0-9]{64}$'},
    'changed_object_ids':{'type':'array','items':s.IDENTITY,'maxItems':32},'interpretation':s.TEXT},
    ['schema_version','baseline','counterfactual','baseline_digest','alternative_digest','changed_object_ids','interpretation'])

def capabilities():
    return {'schema_version':'2.0','coordinate_frame':'world_enu','units':'SI','physical_actuation':False,
            'geometry':['sphere','box_obb','capsule'],'compound_bodies':'explicit_parent_child_hierarchy',
            'continuous_collision':'exact_linear_sphere_and_axis_aligned_box; conservative_other_sweeps',
            'models':['static','constant_acceleration','ground','ballistic','ground_air_hybrid','prismatic'],
            'maximum_result_json_bytes':1_500_000,'maximum_objects':16,'maximum_steps':600,'maximum_pair_intervals':50000,
            'metric_depth':'requires_supplied_depth_or_declared_plane; no_monocular_depth_estimation',
            'cloud_video_jobs':False,'camera_access':'local_edge_only','hardware_validation':'NOT RUN — HARDWARE UNAVAILABLE'}


def _execute(name,request):
    if name not in SCHEMAS: raise ValueError('unknown physical intelligence operation')
    request=s.validate(SCHEMAS[name],request)
    if name=='compare_scene_documents_3d':return world3d.compare_documents(request['baseline'],request['alternative'])
    if name=='closest_approach_3d':
        from engine.geometry3d import closest_approach
        return closest_approach(**request)
    if name=='tracks_to_assumed_scene_3d': return {'scene':assumption_scene(**request)}
    if name=='get_scene_3d': return {'scene':demonstration(request['demo'])}
    if name=='prepare_scene_3d':
        scene=world3d.validate_scene(request['scene'])
        return {'scene':scene,'digest':world3d.digest(scene),'persisted':False}
    if name=='validate_physics_profile': return {'profile':world3d.validate_profile(request['profile']),'validated':True,'applied':False}
    if name=='simulate_scene_3d': return world3d.simulate(request['scene'])
    if name=='simulate_counterfactual_3d': return world3d.compare(request['scene'],request['changes'])
    if name=='upgrade_planar_scene': return {'scene':upgrade_2d(request['scene']),'original_2d':deepcopy(request['scene'])}
    if name=='estimate_kinematics_3d': return estimate_track(**request)
    if name=='calibrate_scene': return pixel_to_world(request['pixel'],request.get('calibration'),depth_m=request.get('depth_m'))
    if name=='extract_video_tracks':
        return sam_tracks(request['segmentation'],request['frame_timestamps_s'],reference=request.get('reference','box_center'),camera_stabilized=request.get('camera_stabilized',False))
    result=world3d.simulate(request['scene'])
    return {'packet':result,'packet_sha256':world3d.digest(result),'signature':None,'authenticity':'unsigned_integrity_only'}


def execute(name,request):
    import json
    result=_execute(name,request)
    if len(json.dumps(result,allow_nan=False).encode())>1_500_000:
        raise ValueError('result budget exceeded; reduce objects, duration or sampling frequency')
    return result


def handle(handler,route,method):
    if not route.startswith('/api/v2/'): return False
    from .workbench_http import body,check_origin
    from .clerk_auth import WorkspaceError
    try:
        check_origin(handler)
        if route=='/api/v2/capabilities' and method=='GET':
            handler._send(200,capabilities());return True
        if route not in ROUTES: raise WorkspaceError(404,'physical_route_not_found')
        if method!='POST': raise WorkspaceError(405,'post_required')
        handler._send(200,execute(ROUTES[route],body(handler)))
    except WorkspaceError as error: handler._send(error.status,{'error':error.code})
    except (ValueError,TypeError,KeyError,OverflowError) as error: handler._send(400,{'error':'invalid_physical_request','detail':str(error)[:200]})
    except Exception: handler._send(503,{'error':'physical_service_unavailable'})
    return True
