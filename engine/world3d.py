"""Versioned deterministic 3D world documents and bounded kinematic simulation.

A collision predictor, not a rigid-contact response/finite-element simulator.
Positions are body/shape centres in right-handed ENU. Child poses are local.
Prismatic joint displacement is along the parent's +Z. No physical actuation.
"""
from __future__ import annotations
from copy import deepcopy
import hashlib
import json
import math
from .spatial3d import Vector3 as V, Quaternion as Q, Pose3D, finite
from . import world3d_schema as contract
from .geometry3d import separation, sweep, extent, radius


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def validate_profile(value):
    profile=contract.validate(contract.PROFILE,value)
    _finite_tree(profile)
    if profile['motion_model']=='ground_air_hybrid' and not profile.get('hypothetical'):
        raise ValueError('ground_air_hybrid requires explicit hypothetical=true')
    if V.read(profile.get('thrust_n',[0,0,0])).norm()/profile['mass_kg']>100:
        raise ValueError('thrust/mass exceeds supported acceleration')
    return profile


def _finite_tree(value):
    if isinstance(value,dict):
        for item in value.values(): _finite_tree(item)
    elif isinstance(value,list):
        for item in value: _finite_tree(item)
    elif isinstance(value,(int,float)) and not isinstance(value,bool): finite(value,low=-1e12,high=1e12)


def validate_scene(value):
    scene=contract.validate(contract.SCENE,value)
    _finite_tree(scene)
    steps=math.ceil(scene['duration_s']/scene['step_s'])
    count=len(scene['objects'])
    if steps>600 or steps*count*(count-1)//2>50000:
        raise ValueError('3D simulation budget exceeded; shorten horizon or increase step')
    cal=scene['calibration']
    if cal['status']=='CALIBRATED_METRIC_3D' and (not cal.get('evidence_id') or cal['method'] in ('simulation','declared_scale')):
        raise ValueError('metric calibration requires non-simulation evidence')
    if cal['status']=='ESTIMATED_3D' and cal['uncertainty_m']<=0:
        raise ValueError('estimated depth requires positive uncertainty')
    seen={};ordered=[];world_orientations={}
    for body in scene['objects']:
        if body['id'] in seen: raise ValueError('duplicate 3D identity')
        profile=validate_profile(body['physics'])
        pose=body['pose'];Q.read(pose.get('orientation_wxyz',[1,0,0,0]))
        p=V.read(pose['position_m'])
        velocity=V.read(body.get('velocity_mps',[0,0,0]))
        accel=V.read(body.get('acceleration_mps2',[0,0,0]))
        if math.hypot(velocity.x,velocity.y)>profile['max_horizontal_speed_mps']+1e-9 or abs(velocity.z)>profile['max_vertical_speed_mps']+1e-9:
            raise ValueError('initial velocity exceeds physics profile')
        if accel.norm()>profile['max_acceleration_mps2']+1e-9: raise ValueError('acceleration exceeds profile')
        if V.read(body.get('angular_velocity_radps',[0,0,0])).norm()>profile.get('max_angular_speed_radps',0)+1e-9:
            raise ValueError('angular velocity exceeds profile')
        if body.get('waypoints'):
            from .trajectory3d import validate as validate_trajectory
            if profile['motion_model'] not in ('ground','constant_acceleration'): raise ValueError('waypoints require ground or constant_acceleration kinematic profile')
            if body.get('parent_id') or velocity.norm() or accel.norm(): raise ValueError('waypoints cannot combine with attachment or free initial motion')
            validate_trajectory(body['waypoints'],profile,pose['position_m'],profile['motion_model']=='ground')
        parent=body.get('parent_id')
        if parent and parent not in seen: raise ValueError('parents must precede children; cycles and missing parents forbidden')
        if body.get('joint'):
            joint=body['joint']
            if not parent or profile['motion_model']!='prismatic': raise ValueError('joint requires prismatic child')
            if max(joint['initial_m'],joint['target_m'])>joint['max_travel_m']: raise ValueError('joint exceeds travel')
            if joint['speed_mps']>profile['max_vertical_speed_mps'] or joint['acceleration_mps2']>profile['max_acceleration_mps2']:
                raise ValueError('joint exceeds actuator profile')
            parent_pose=seen[parent]['pose']
            if world_orientations[parent].rotate(V(0,0,1)).z<1-1e-9:
                raise ValueError('prismatic_z requires upright parent')
        elif profile['motion_model']=='prismatic': raise ValueError('prismatic profile requires joint')
        if parent and not body.get('joint') and body.get('attachment')!='rigid_assumption': raise ValueError('child attachment must be explicit')
        if parent and any(body.get(k,[0,0,0])!=[0,0,0] for k in ('velocity_mps','acceleration_mps2','angular_velocity_radps')):
            raise ValueError('children cannot have independent free-body motion')
        if profile['motion_model']=='static' and (velocity.norm() or accel.norm() or V.read(body.get('angular_velocity_radps',[0,0,0])).norm()): raise ValueError('static object cannot move')
        if body['provenance']=='HARDWARE_OBSERVATION' and cal['status']=='ASSUMPTION_3D': raise ValueError('hardware metric pose requires calibration or estimated-depth metadata')
        if not parent and profile['motion_model']=='ground' and abs(p.z-extent(body['geometry'],Pose3D(p,Q.read(pose.get('orientation_wxyz',[1,0,0,0])))).z)>1e-6:
            raise ValueError('ground body centre must place its collision bottom on z=0')
        world_orientations[body['id']]=(world_orientations[parent].compose(Q.read(pose.get('orientation_wxyz',[1,0,0,0]))) if parent else Q.read(pose.get('orientation_wxyz',[1,0,0,0])))
        seen[body['id']]=body;ordered.append(body)
    parent_ids={b['parent_id'] for b in ordered if b.get('parent_id')}
    for key in parent_ids:
        if V.read(seen[key].get('angular_velocity_radps',[0,0,0])).norm():
            raise ValueError('rotating articulated parents are not supported by this version')
    for pair in scene.get('excluded_pairs',[]):
        if pair[0]==pair[1] or any(k not in seen for k in pair): raise ValueError('invalid excluded collision pair')
    return scene


def joint_at(joint,t):
    """Analytic rest-to-rest trapezoidal/triangular actuator profile."""
    delta=joint['target_m']-joint['initial_m'];direction=1 if delta>=0 else -1
    distance=abs(delta);a=joint['acceleration_mps2'];speed=joint['speed_mps']
    ramp=min(speed/a,math.sqrt(distance/a));peak=a*ramp
    coast=(distance-a*ramp*ramp)/peak if peak else 0
    total=2*ramp+coast;elapsed=max(0.,t-joint['start_s'])
    if elapsed>=total: return joint['target_m'],0.,0.
    if elapsed<ramp: pos,vel,acc=.5*a*elapsed**2,a*elapsed,a
    elif elapsed<ramp+coast: pos,vel,acc=.5*a*ramp**2+peak*(elapsed-ramp),peak,0.
    else:
        left=total-elapsed;pos,vel,acc=distance-.5*a*left**2,a*left,-a
    if t<joint['start_s']: return joint['initial_m'],0.,0.
    return joint['initial_m']+direction*pos,direction*vel,direction*acc


def _advance(p,v,a,dt,profile):
    # Exact constant-acceleration position until a speed limit is reached; vector
    # horizontal cap is enforced after integration and recorded as a constraint.
    end=v+a*dt
    limit=profile['max_vertical_speed_mps']
    zspeed=max(-limit,min(limit,end.z))
    zdist=v.z*dt+.5*a.z*dt*dt
    if a.z and zspeed!=end.z:
        cap=max(0.,min(dt,(zspeed-v.z)/a.z))
        zdist=v.z*cap+.5*a.z*cap*cap+zspeed*(dt-cap)
    h=math.hypot(end.x,end.y);hlimit=profile['max_horizontal_speed_mps']
    scale=min(1.,hlimit/h) if h else 1.
    candidate=p+V(v.x*dt+.5*a.x*dt*dt,v.y*dt+.5*a.y*dt*dt,zdist)
    # Clipping speed after this step is a bounded approximation for turning;
    # analytic constant-acceleration tests operate below the declared cap.
    if h>hlimit:
        candidate=V(p.x+(v.x+end.x*scale)*dt/2,p.y+(v.y+end.y*scale)*dt/2,candidate.z)
    return candidate,V(end.x*scale,end.y*scale,zspeed),h>hlimit or zspeed!=end.z


def _acceleration_bound(body,by_id):
    if body.get('parent_id'):
        return _acceleration_bound(by_id[body['parent_id']],by_id)+body.get('joint',{}).get('acceleration_mps2',0.)
    if body.get('waypoints'):
        return max(10*math.sqrt(3)/3*(V.read(b['position_m'])-V.read(a['position_m'])).norm()/(b['t_s']-a['t_s'])**2
                   for a,b in zip(body['waypoints'],body['waypoints'][1:]))
    p=body['physics']
    if p['motion_model']=='static': return 0.
    acceleration=V.read(body.get('acceleration_mps2',[0,0,0]))
    if p['motion_model'] in ('ballistic','ground_air_hybrid'):
        acceleration=acceleration+V.read(p.get('thrust_n',[0,0,0]))*(1/p['mass_kg'])-V(0,0,p['gravity_mps2'])
    return min(p['max_acceleration_mps2'],acceleration.norm()+p.get('linear_drag_per_s',0)*math.hypot(p['max_horizontal_speed_mps'],p['max_vertical_speed_mps']))


def simulate(value):
    scene=validate_scene(value)
    bodies=scene['objects'];by_id={b['id']:b for b in bodies};states={};frames=[];events=[];constraints=[];minimum={};previous=None
    excluded={frozenset(p) for p in scene.get('excluded_pairs',[])}
    for body in bodies:
        states[body['id']]={'pose':Pose3D(V.read(body['pose']['position_m']),Q.read(body['pose'].get('orientation_wxyz',[1,0,0,0]))),
                            'velocity':V.read(body.get('velocity_mps',[0,0,0])),'acceleration':V()}
    count=math.ceil(scene['duration_s']/scene['step_s'])
    for carrier in bodies:
        limit=carrier['physics'].get('max_payload_kg')
        if limit is not None:
            load=0.
            for candidate in bodies:
                ancestor=candidate.get('parent_id')
                while ancestor and ancestor!=carrier['id']:ancestor=by_id[ancestor].get('parent_id')
                if ancestor==carrier['id'] and candidate.get('load_bearing_payload'):load+=candidate['physics']['mass_kg']
            if load>limit:constraints.append({'object_id':carrier['id'],'t_s':0.,'code':'payload_capacity','load_kg':load,'limit_kg':limit})
    for index in range(count+1):
        t=min(index*scene['step_s'],scene['duration_s']);dt=0 if index==0 else t-frames[-1]['t_s']
        current={}
        for body in bodies:
            key=body['id'];profile=body['physics'];model=profile['motion_model'];local=states[key]
            pose=local['pose'];velocity=local['velocity'];acceleration=V()
            if body.get('parent_id'):
                parent=current[body['parent_id']]
                local_pose=Pose3D(V.read(body['pose']['position_m']),Q.read(body['pose'].get('orientation_wxyz',[1,0,0,0])))
                speed=0.
                if body.get('joint'):
                    travel,speed,acc=joint_at(body['joint'],t)
                    local_pose=Pose3D(local_pose.position+V(0,0,travel),local_pose.orientation)
                pose=parent['pose'].compose(local_pose)
                # Actual centre derivative includes parent rotation. At t=0 use
                # declared parent linear velocity plus prismatic velocity.
                velocity=(pose.position-previous[key]['pose'].position)*(1/dt) if dt else parent['velocity']+parent['pose'].orientation.rotate(V(0,0,speed))
                acceleration=(velocity-previous[key]['velocity'])*(1/dt) if dt else V()
            elif body.get('waypoints'):
                from .trajectory3d import at
                p,velocity,acceleration=at(body['waypoints'],t)
                pose=Pose3D(p,pose.orientation.advance(V.read(body.get('angular_velocity_radps',[0,0,0])),dt))
            elif index and model!='static':
                acceleration=V.read(body.get('acceleration_mps2',[0,0,0]))
                if model in ('ballistic','ground_air_hybrid'):
                    acceleration=acceleration+V.read(profile.get('thrust_n',[0,0,0]))*(1/profile['mass_kg'])-V(0,0,profile['gravity_mps2'])
                acceleration=acceleration-velocity*profile.get('linear_drag_per_s',0)
                if acceleration.norm()>profile['max_acceleration_mps2']+1e-8: raise ValueError('net acceleration exceeds declared profile')
                p,velocity,limited=_advance(pose.position,velocity,acceleration,dt,profile)
                orientation=pose.orientation.advance(V.read(body.get('angular_velocity_radps',[0,0,0])),dt)
                pose=Pose3D(p,orientation)
                if model in ('ground','ground_air_hybrid'):
                    floor=extent(body['geometry'],pose).z
                    if model=='ground' or p.z<floor:
                        pose=Pose3D(V(p.x,p.y,floor),orientation);velocity=V(velocity.x,velocity.y,0)
                acceleration=(velocity-local['velocity'])*(1/dt)
                if limited and not any(e['object_id']==key and e['code']=='speed_limit' for e in constraints):
                    constraints.append({'object_id':key,'t_s':t,'code':'speed_limit'})
            current[key]={'pose':pose,'velocity':velocity,'acceleration':acceleration}
            states[key]=current[key]
        for i,a in enumerate(bodies):
            sa=current[a['id']]
            if a['physics']['motion_model']=='ground':
                descendants=[b for b in bodies if b.get('parent_id')==a['id'] and b.get('joint')]
                if descendants:
                    height=max(joint_at(b['joint'],t)[0] for b in descendants)
                    speed=math.hypot(sa['velocity'].x,sa['velocity'].y)
                    if height>a['physics'].get('elevated_above_m',1e6) and speed>a['physics'].get('elevated_speed_limit_mps',200):
                        if not any(e['code']=='elevated_load_speed' and e['object_id']==a['id'] for e in constraints):
                            constraints.append({'object_id':a['id'],'t_s':t,'code':'elevated_load_speed','height_m':height,'speed_mps':speed})
            for b in bodies[i+1:]:
                pair=(a['id'],b['id'])
                if frozenset(pair) in excluded: continue
                sb=current[b['id']]
                gap,contact,method=separation(a['geometry'],sa['pose'],b['geometry'],sb['pose'])
                row=minimum.setdefault('|'.join(pair),{'objects':list(pair),'clearance_m':gap,'at_s':t,'method':method})
                if gap<row['clearance_m']: row.update(clearance_m=gap,at_s=t,method=method)
                if contact and not any(e['objects']==list(pair) and e['kind']=='CONTACT' for e in events):
                    events.append({'objects':list(pair),'kind':'CONTACT','t_s':t,'clearance_m':gap,'method':method})
                if previous:
                    # Curved-centre uncertainty bound; use profile maximums for
                    # articulated/rotating centres and exact zero for linear paths.
                    margin=(_acceleration_bound(a,by_id)+_acceleration_bound(b,by_id))*dt*dt/8
                    margin+=a.get('uncertainty_radius_m',0)+b.get('uncertainty_radius_m',0)+2*scene['calibration']['uncertainty_m']
                    for rotating in (a,b):
                        omega=V.read(rotating.get('angular_velocity_radps',[0,0,0])).norm()
                        margin+=radius(rotating['geometry'])*min(2.,omega*dt)
                    fraction,sweep_method=sweep(a['geometry'],previous[a['id']]['pose'],sa['pose'],b['geometry'],previous[b['id']]['pose'],sb['pose'],margin)
                    if fraction is not None:
                        kind='CONTACT' if sweep_method.startswith('exact') else 'POSSIBLE_CONTACT'
                        if kind=='CONTACT' and row['clearance_m']>0:
                            row.update(clearance_m=0.,at_s=t-dt+fraction*dt,method='swept_contact_zero_upper_bound')
                        if not any(e['objects']==list(pair) and e['kind']==kind for e in events):
                            events.append({'objects':list(pair),'kind':kind,'t_s':t-dt+fraction*dt,'method':sweep_method})
        frames.append({'t_s':t,'objects':[{"id":b['id'],**current[b['id']]['pose'].document(),
                         'velocity_mps':current[b['id']]['velocity'].array(),'acceleration_mps2':current[b['id']]['acceleration'].array(),
                         'ground_clearance_m':current[b['id']]['pose'].position.z-extent(b['geometry'],current[b['id']]['pose']).z}
                        for b in bodies]})
        previous=current
    return {'schema_version':'2.0','coordinate_frame':'world_enu','units':'SI','source_digest':digest(scene),'scene':scene,
            'provenance':'DETERMINISTIC','calibration':scene['calibration'],'frames':frames,'events':events,'constraints':constraints,
            'minimum_clearances':list(minimum.values()),'labels':{'simulation_only':True,'physical_actuation':False,
            'contact_response':False,'clearances_include_conservative_bounds':True,'clearance_sampling':'minimum_of_emitted_frames; continuous contacts reported separately','acceleration_interpretation':'Free-body interval mean after constraints; analytic waypoint derivative; articulated finite differences; initial free-body sample unavailable (zero sentinel).'},
            'assumptions':scene['assumptions']+['Fixed-step kinematic prediction; no contact response, tipping, structural compliance or aerodynamic validation.']}


def compare(scene,changes):
    """Typed body profile/joint/state overrides. Never modifies the source."""
    if not isinstance(changes,list) or not 1<=len(changes)<=16: raise ValueError('1..16 object changes required')
    altered=deepcopy(validate_scene(scene));seen=set();by_id={o['id']:o for o in altered['objects']}
    for change in changes:
        if not isinstance(change,dict) or set(change)-{'object_id','physics','joint','pose','velocity_mps','acceleration_mps2','waypoints','geometry','angular_velocity_radps'}:
            raise ValueError('unsupported intervention')
        identity=change.get('object_id')
        if identity not in by_id or identity in seen: raise ValueError('unknown or duplicate intervention object')
        seen.add(identity)
        for key,value in change.items():
            if key!='object_id': by_id[identity][key]=deepcopy(value)
        if 'physics' in change:by_id[identity]['physics_provenance']='ASSUMPTION'
        if any(k in change for k in ('pose','geometry','velocity_mps','acceleration_mps2','waypoints','joint')):by_id[identity]['provenance']='ASSUMPTION'
    return {'schema_version':'2.0','baseline':simulate(scene),'counterfactual':simulate(altered),'changes':deepcopy(changes),
            'interpretation':'Conditional simulations under declared assumptions, not causal proof or hardware authorization.'}


def compare_documents(baseline,alternative):
    """Compare complete canonical revisions, including added/removed components."""
    baseline=validate_scene(baseline);alternative=validate_scene(alternative)
    left={o['id']:o for o in baseline['objects']};right={o['id']:o for o in alternative['objects']}
    changed=sorted(key for key in left.keys()|right.keys() if left.get(key)!=right.get(key))
    return {'schema_version':'2.0','baseline':simulate(baseline),'counterfactual':simulate(alternative),
            'baseline_digest':digest(baseline),'alternative_digest':digest(alternative),'changed_object_ids':changed,
            'interpretation':'Independent canonical scene revisions; conditional kinematic comparison, not causal proof or hardware authorization.'}
