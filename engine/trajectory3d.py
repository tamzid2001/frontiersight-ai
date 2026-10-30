"""C2 rest-to-rest 3D waypoint segments with analytic derivative limits."""
import math
from .spatial3d import Vector3 as V


def validate(waypoints,physics,initial,ground=False):
    if not isinstance(waypoints,list) or not 2<=len(waypoints)<=16: raise ValueError('2..16 timed waypoints required')
    if waypoints[0]['t_s']!=0 or waypoints[0]['position_m']!=initial: raise ValueError('trajectory must start at the initial pose at t=0')
    for a,b in zip(waypoints,waypoints[1:]):
        dt=b['t_s']-a['t_s']
        if dt<=0: raise ValueError('waypoint times must strictly increase')
        delta=V.read(b['position_m'])-V.read(a['position_m'])
        if ground and abs(delta.z)>1e-9: raise ValueError('ground waypoints cannot lift the chassis')
        if 1.875*math.hypot(delta.x,delta.y)/dt>physics['max_horizontal_speed_mps']+1e-9: raise ValueError('waypoint horizontal speed exceeds profile')
        if 1.875*abs(delta.z)/dt>physics['max_vertical_speed_mps']+1e-9: raise ValueError('waypoint vertical speed exceeds profile')
        if 10*math.sqrt(3)/3*delta.norm()/dt**2>physics['max_acceleration_mps2']+1e-9: raise ValueError('waypoint acceleration exceeds profile')
    return waypoints


def at(waypoints,t):
    if t>=waypoints[-1]['t_s']: return V.read(waypoints[-1]['position_m']),V(),V()
    for a,b in zip(waypoints,waypoints[1:]):
        if t<=b['t_s']:
            dt=b['t_s']-a['t_s'];u=max(0.,(t-a['t_s'])/dt)
            delta=V.read(b['position_m'])-V.read(a['position_m'])
            s=10*u**3-15*u**4+6*u**5
            ds=(30*u**2-60*u**3+30*u**4)/dt
            dds=(60*u-180*u**2+120*u**3)/(dt*dt)
            return V.read(a['position_m'])+delta*s,delta*ds,delta*dds
    raise ValueError('unreachable trajectory interval')
