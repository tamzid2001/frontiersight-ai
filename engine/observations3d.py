"""Timestamp-aware observations, explicit camera calibration, alpha-beta estimates.

Reported model confidence is not calibrated geometric uncertainty. Sigma is a
caller-declared observation error bound. Motion is an estimate, never ground truth.
"""
from __future__ import annotations
import math
from .spatial3d import Vector3 as V, Quaternion as Q, Pose3D, finite


def pixel_to_world(pixel, calibration, *, depth_m=None):
    """Pinhole optical (right/down/forward) -> ENU using an explicit extrinsic.

    Metric depth is along optical +Z (not radial range). A ray-plane intersection
    requires a declared horizontal plane. A single monocular image supplies none.
    Returns propagated conservative first-order error, not a calibrated confidence.
    """
    if not isinstance(pixel,(list,tuple)) or len(pixel)!=2: raise ValueError('pixel requires u,v')
    u,v=[finite(x,'pixel',0,16384) for x in pixel]
    if not isinstance(calibration,dict): return {'status':'DEPTH_UNAVAILABLE','pixel':[u,v],'position_m':None}
    allowed={'fx','fy','cx','cy','camera_pose','plane_z_m','evidence_id','pixel_sigma','depth_sigma_m','source'}
    if set(calibration)-allowed: raise ValueError('unknown camera calibration field')
    fx,fy=[finite(calibration.get(k),k,.001,1e6) for k in ('fx','fy')]
    cx,cy=[finite(calibration.get(k),k,0,16384) for k in ('cx','cy')]
    pose=calibration.get('camera_pose',{})
    origin=V.read(pose.get('position_m'));q=Q.read(pose.get('orientation_wxyz'))
    optical=V((u-cx)/fx,(v-cy)/fy,1.)
    ray=q.rotate(optical)
    sigma=finite(calibration.get('pixel_sigma',1),'pixel_sigma',0,100)
    depth_sigma=finite(calibration.get('depth_sigma_m',0),'depth_sigma_m',0,100)
    if depth_m is not None:
        depth=finite(depth_m,'optical depth',.001,10000)
        point=origin+ray*depth
        status='CALIBRATED_METRIC_3D' if calibration.get('evidence_id') and calibration.get('source')=='depth_sensor' else 'ESTIMATED_3D'
        uncertainty=depth*math.sqrt((sigma/fx)**2+(sigma/fy)**2)+ray.norm()*depth_sigma
        if status=='ESTIMATED_3D' and uncertainty<=0: raise ValueError('estimated depth requires uncertainty')
        assumptions=['Pinhole camera, rectified pixels; uncertainty excludes extrinsic error unless included by caller.']
    elif 'plane_z_m' in calibration:
        plane=finite(calibration['plane_z_m'],'plane_z_m')
        if abs(ray.z)<1e-8: raise ValueError('camera ray is parallel to declared plane')
        depth=(plane-origin.z)/ray.z
        if depth<=0: raise ValueError('declared plane is behind camera')
        point=origin+ray*depth;status='ASSUMPTION_3D'
        # Near-grazing rays amplify pixel uncertainty; explicit denominator.
        uncertainty=depth*sigma/min(fx,fy)*(1+ray.norm()/abs(ray.z))
        assumptions=['Reference point lies on user-declared plane, not a measured object height.']
    else: return {'status':'DEPTH_UNAVAILABLE','pixel':[u,v],'position_m':None}
    return {'status':status,'position_m':point.array(),'uncertainty_radius_m':uncertainty,
            'evidence_id':calibration.get('evidence_id'),'assumptions':assumptions}


def estimate_track(points,*,alpha=.7,beta=.15,max_gap_s=1.,observation_sigma=1.,camera_stabilized=False):
    """Variable-dt alpha-beta filter with reset on long occlusion/discontinuity.

    points: {t_s, position:[x,y,(z)], confidence?, identity_continuous?}.
    Filtering is done in the supplied coordinate system; no pixel/metre conversion.
    Missing observations are omitted, not interpolated as measured positions.
    """
    alpha=finite(alpha,'alpha',.001,1);beta=finite(beta,'beta',0,1)
    max_gap_s=finite(max_gap_s,'max_gap_s',.001,60)
    sigma=finite(observation_sigma,'observation_sigma',.000001,1000)
    if not isinstance(points,list) or not 2<=len(points)<=5000: raise ValueError('track requires 2..5000 observations')
    out=[];prior=None;dimensions=None
    for row in points:
        if not isinstance(row,dict) or set(row)-{'t_s','position','confidence','identity_continuous','frame_index'}: raise ValueError('invalid observation fields')
        t=finite(row.get('t_s'),'timestamp',0,1e12);position=row.get('position')
        if not isinstance(position,list) or len(position) not in (2,3): raise ValueError('observation position must have 2 or 3 components')
        if dimensions is not None and dimensions!=len(position): raise ValueError('track coordinate dimensions changed')
        dimensions=len(position);p=V.read(position+([0] if dimensions==2 else []))
        confidence=row.get('confidence')
        if confidence is not None: confidence=finite(confidence,'confidence',0,1)
        continuous=row.get('identity_continuous',True)
        if not isinstance(continuous,bool): raise ValueError('identity_continuous must be boolean')
        dt=t-prior['t_s'] if prior else 0
        if prior and dt<=0: raise ValueError('observation timestamps must increase strictly')
        reset=prior is None or dt>max_gap_s or not continuous
        diagnostic='initial' if prior is None else 'occlusion_reset' if dt>max_gap_s else 'identity_reset' if not continuous else None
        old_v=V.read(prior['velocity']) if prior else V()
        if reset: estimate,velocity,acceleration=p,V(),V()
        else:
            predicted=V.read(prior['filtered_position'])+old_v*dt
            residual=p-predicted;estimate=predicted+residual*alpha
            velocity=old_v+residual*(beta/dt);acceleration=(velocity-old_v)*(1/dt)
        record={'t_s':t,'observed_position':p.array(),'filtered_position':estimate.array(),'velocity':velocity.array(),
                'acceleration':acceleration.array(),'velocity_available':not reset,'confidence':confidence,
                'uncertainty_radius':sigma if reset else sigma+old_v.norm()*dt*(1-alpha),
                'diagnostic':diagnostic,'provenance':'DETERMINISTIC','source_provenance':'MODEL_DERIVED'}
        out.append(record);prior=record
    return {'observations':out,'coordinate_dimensions':dimensions,'units':'unchanged_input_units',
            'motion_interpretation':'world_motion_estimate' if camera_stabilized else 'apparent_motion_camera_motion_unresolved',
            'uncertainty_method':'declared_error_plus_prediction_growth_not_empirical_confidence_interval',
            'filter':{'type':'alpha_beta','alpha':alpha,'beta':beta,'max_gap_s':max_gap_s}}


def sam_tracks(parsed,frame_timestamps,*,reference='box_center',camera_stabilized=False):
    """Extract within-response SAM identities using actual decoded presentation times.

    Supports box centre and bottom centre. Decoded mask centroid can be supplied
    only when the parser provides a genuine centroid; no invented mask geometry.
    """
    if reference not in ('box_center','bottom_center','mask_centroid'): raise ValueError('unsupported tracking reference')
    if not isinstance(frame_timestamps,list) or not 1<=len(frame_timestamps)<=100000: raise ValueError('frame timestamp table required')
    times=[finite(t,'presentation timestamp',0,1e9) for t in frame_timestamps]
    if any(b<=a for a,b in zip(times,times[1:])): raise ValueError('frame PTS must increase strictly')
    tracks={};last=-1
    for frame in parsed.get('frames',[]):
        index=frame['frame']
        if not isinstance(index,int) or index<=last or not 0<=index<len(times): raise ValueError('SAM frame index does not match source PTS')
        last=index;seen=set()
        for row in frame['records']:
            identity=str(row['object_id'])
            if identity in seen: raise ValueError('duplicate SAM identity within frame')
            seen.add(identity);box=row['box']
            point=[(box['x1']+box['x2'])/2,(box['y1']+box['y2'])/2]
            if reference=='bottom_center': point[1]=box['y2']
            if reference=='mask_centroid':
                mask=row.get('mask',{})
                if not mask.get('decoded') or mask.get('centroid_px') is None: raise ValueError('genuine decoded mask centroid unavailable')
                point=mask['centroid_px']
            tracks.setdefault(identity,[]).append({'t_s':times[index],'position':point,'confidence':row.get('confidence'),'frame_index':index})
    return {'space':'pixel','calibration_status':'PIXEL_ONLY_2D','depth_available':False,
            'identity_scope':'single_model_response; re-entry/full occlusion may change identity',
            'tracks':[{'object_id':identity,'points':points,'kinematics':estimate_track(points,camera_stabilized=camera_stabilized) if len(points)>=2 else None}
                      for identity,points in tracks.items()]}


def assumption_scene(tracks,metres_per_pixel,height_m=0.,radius_m=.25):
    """Explicit user scale/height assumption; never calibrated monocular depth."""
    from .demos3d import profile,base
    from .world3d import validate_scene
    scale=finite(metres_per_pixel,'assumed_metres_per_pixel',.000001,100)
    height=finite(height_m,'assumed_elevation_m',0,100)
    radius=finite(radius_m,'assumed_radius_m',.001,20)
    if not isinstance(tracks,list) or not 1<=len(tracks)<=16: raise ValueError('1..16 tracks required for scene conversion')
    objects=[]
    try: common=max(track['points'][-1]['t_s'] for track in tracks)
    except (KeyError,IndexError,TypeError):raise ValueError('valid timestamped tracks required') from None
    for track in tracks:
        rows=track.get('points',[])
        estimates=estimate_track(rows,observation_sigma=1.)
        last=estimates['observations'][-1];p=last['filtered_position'];v=last['velocity']
        age=common-last['t_s']
        if age>1:raise ValueError('track endpoints are more than one second apart; align observations before world conversion')
        p=[p[i]+v[i]*age for i in range(3)]
        uncertainty=(last['uncertainty_radius']+age*math.hypot(v[0],v[1]))*scale
        if uncertainty>100:raise ValueError('assumed spatial uncertainty exceeds supported bound')
        identity=track.get('object_id')
        objects.append({'id':identity,'pose':{'position_m':[p[0]*scale,-p[1]*scale,height+radius]},
            'velocity_mps':[v[0]*scale,-v[1]*scale,0.], 'geometry':{'kind':'sphere','radius_m':radius},
            'physics':profile('constant_acceleration',max_horizontal_speed_mps=200),
            'uncertainty_radius_m':uncertainty,'provenance':'ASSUMPTION'})
    scene=base('Video tracks: assumed scale and constant elevation',objects,3.)
    scene['source_time_s']=common
    scene['calibration']['method']='declared_scale'
    scene['calibration']['uncertainty_m']=scale
    scene['calibration']['assumptions']=[f'User-assumed isotropic scale {scale} m/pixel and constant elevation {height} m; camera motion/perspective unresolved.']
    scene['assumptions']+=['Initial-state predictions from per-track last observation; differing track end times require alignment before joint measured-world interpretation.',
                           'Camera pixels u/v map to ENU +X/-Y; radius, depth, perspective and constant height are assumptions.']
    return validate_scene(scene)
