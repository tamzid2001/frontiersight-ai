"""Synthetic engineering demonstrations, never measured industrial operations."""
from copy import deepcopy
from .world3d import validate_scene


def profile(model='static',**overrides):
    result={'schema_version':'2.0','motion_model':model,'mass_kg':100.,'max_horizontal_speed_mps':5.,
            'max_vertical_speed_mps':5.,'max_acceleration_mps2':20.,'gravity_mps2':9.80665,
            'max_angular_speed_radps':2.,'assumptions':['Declared illustrative dynamics, not manufacturer specifications.']}
    result.update(overrides)
    return result


def body(identity,position,half,model='static',**kw):
    result={'id':identity,'label':identity.replace('-',' ').title(),'pose':{'position_m':position},
            'geometry':{'kind':'box','half_extents_m':half},'physics':profile(model),'provenance':'FIXTURE'}
    result.update(kw)
    return result


def base(name,objects,duration=12):
    return {'schema_version':'2.0','coordinate_frame':'world_enu','units':'SI','name':name,'duration_s':duration,'step_s':.1,
            'calibration':{'status':'ASSUMPTION_3D','method':'simulation','uncertainty_m':0.,
                           'assumptions':['All geometry and dynamics are synthetic declared SI inputs.']},
            'objects':objects,'assumptions':['No hardware connection. No physical safety certification.']}


def warehouse():
    chassis=body('chassis',[2,4,.65],[.85,.55,.65],'ground',velocity_mps=[.4,0,0],
                 physics=profile('ground',mass_kg=3500,max_payload_kg=1000,elevated_above_m=.8,elevated_speed_limit_mps=.3))
    # Approach stops at x=4; ground acceleration makes it stop after five seconds.
    # A stopped chassis baseline uses an explicit maximum travel command through
    # the demo fixture's initial state rather than any fake height animation.
    chassis['velocity_mps']=[0,0,0];chassis['pose']['position_m']=[4,4,.65]
    mast=body('mast',[.7,0,1.5],[.12,.5,1.5],parent_id='chassis',attachment='rigid_assumption')
    forks=body('forks',[1.3,0,-.5],[.65,.45,.06],'prismatic',parent_id='chassis',
               joint={'type':'prismatic_z','start_s':1.,'initial_m':0.,'target_m':2.6,'max_travel_m':4.,'speed_mps':.35,'acceleration_mps2':.5})
    payload=body('payload',[0,0,.36],[.6,.45,.3],parent_id='forks',attachment='rigid_assumption',physics=profile(mass_kg=900))
    shelf=body('shelf-deck',[6.65,4,2.6],[.65,.75,.1])
    beam=body('overhead-beam',[5.3,4,3.8],[.3,.9,.1])
    person=body('person',[5.3,6,.85],[.25,.25,.85])
    result=base('Warehouse vertical lift (attached-payload assumption)',[chassis,mast,forks,payload,shelf,beam,person])
    # Collision exclusions are explicit and evidence-exported, only for mechanically
    # connected components. Payload/shelf/beam contacts remain evaluated.
    result['excluded_pairs']=[['chassis','mast'],['chassis','forks'],['chassis','payload'],['mast','forks'],['mast','payload'],['forks','payload']]
    result['assumptions']+=['Payload remains rigidly attached: release/placement is not simulated.',
                            'Chassis is already aligned and stationary in the baseline; compare an approach velocity as an intervention.']
    return validate_scene(result)


def flying():
    car=body('flying-vehicle',[1,4,1.],[.8,.5,.4],'ground_air_hybrid',velocity_mps=[1,0,0],
             acceleration_mps2=[0,0,1.],physics=profile('ground_air_hybrid',mass_kg=1600,hypothetical=True,
             thrust_n=[0,0,1600*9.80665],max_vertical_speed_mps=3.,max_acceleration_mps2=20.))
    human=body('ground-person',[5,4,.85],[.25,.25,.85])
    obstacle=body('gantry',[9,4,2.],[.4,1.5,2.])
    result=base('Hypothetical vertical-thrust vehicle',[car,human,obstacle],8)
    result['assumptions']+=['Idealized thrust cancels gravity; additional +Z acceleration is hypothetical.',
                            'No real vehicle flight capability or aerodynamic/stability model.']
    return validate_scene(result)


def demonstration(name):
    if name=='warehouse': return warehouse()
    if name=='flying': return flying()
    raise ValueError('unknown 3D demonstration')


def upgrade_2d(value):
    """Explicit assumption-based conversion; source paths use declared SI scale.

    A new centre sits one radius above ground so its collision bottom touches z=0.
    Initial horizontal velocity follows the first nonzero segment. The full
    curved path is preserved in the original 2D document; it is NOT silently
    claimed as the free-body trajectory in this new prediction.
    """
    from .scene_edit import validate_document
    scene=validate_document(value);objects=[]
    for obj in scene['objects']:
        points=obj['waypoints'];r=max(.01,obj.get('radius',.3))
        first=points[0];velocity=[0.,0.,0.]
        for point in points[1:]:
            dx,dy=point[0]-first[0],point[1]-first[1];distance=(dx*dx+dy*dy)**.5
            if distance:
                speed=obj.get('speed',0);velocity=[speed*dx/distance,speed*dy/distance,0.];break
        objects.append({'id':obj.get('id',obj.get('object_id')),'pose':{'position_m':[first[0],first[1],r]},
                        'velocity_mps':velocity,'geometry':{'kind':'sphere','radius_m':r},'physics':profile('constant_acceleration',max_horizontal_speed_mps=200),
                        'provenance':'ASSUMPTION'})
    if not objects: raise ValueError('2D conversion requires an object')
    result=base('Planar scene: initial-state 3D prediction',objects,5.)
    result['assumptions']+=['2D x/y map to ENU x/y; body centre z=radius keeps ground contact.',
                            'Height, sphere geometry and constant initial tangent velocity are assumptions; original path-following scene is unchanged.']
    return validate_scene(result)
