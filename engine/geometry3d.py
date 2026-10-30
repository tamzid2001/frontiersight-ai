"""3D collision queries. Exact supported queries and conservative bounds are explicit.

No mesh/contact solver. OBB overlap uses 15-axis SAT; its positive gap is a
lower bound on distance. Swept enclosing boxes are conservative for capsules,
rotations and curved motion: a possible contact is never labelled a measured hit.
"""
from __future__ import annotations
import math
from .spatial3d import Vector3 as V, Pose3D, segment_distance

AXES=(V(1,0,0),V(0,1,0),V(0,0,1))


def axes(pose): return tuple(pose.orientation.rotate(v) for v in AXES)


def radius(geometry):
    if geometry['kind']=='sphere': return geometry['radius_m']
    if geometry['kind']=='capsule': return geometry['radius_m']+geometry['half_length_m']
    return V.read(geometry['half_extents_m']).norm()


def extent(geometry, pose):
    if geometry['kind']=='sphere': return V(*(geometry['radius_m'],)*3)
    if geometry['kind']=='capsule':
        a=axes(pose)[2].array()
        return V(*(abs(v)*geometry['half_length_m']+geometry['radius_m'] for v in a))
    basis=axes(pose)
    return V(*(sum(abs(basis[j].array()[i])*geometry['half_extents_m'][j] for j in range(3)) for i in range(3)))


def aabb_gap(pa, ea, pb, eb):
    gaps=[abs(x-y)-a-b for x,y,a,b in zip(pa.array(),pb.array(),ea.array(),eb.array())]
    positive=[max(0.,g) for g in gaps]
    return math.sqrt(sum(g*g for g in positive)) if any(positive) else max(gaps)


def _sphere_box(sphere, sp, box, bp):
    local=bp.orientation.inverse().rotate(sp.position-bp.position).array()
    gaps=[abs(x)-h for x,h in zip(local,box['half_extents_m'])]
    return (math.sqrt(sum(max(0.,g)**2 for g in gaps)) if max(gaps)>0 else max(gaps))-sphere['radius_m']


def separation(a, pa, b, pb):
    """Return signed clearance, collision boolean, and precision description."""
    ka,kb=a['kind'],b['kind']
    if ka==kb=='sphere':
        gap=(pa.position-pb.position).norm()-a['radius_m']-b['radius_m']
        return gap,gap<=0,'exact_sphere'
    if ka=='sphere' and kb=='box':
        gap=_sphere_box(a,pa,b,pb)
        return gap,gap<=0,'exact_sphere_obb'
    if kb=='sphere' and ka=='box': return separation(b,pb,a,pa)
    if ka in ('sphere','capsule') and kb in ('sphere','capsule'):
        ha=a.get('half_length_m',0);hb=b.get('half_length_m',0)
        ua=axes(pa)[2]*ha;ub=axes(pb)[2]*hb
        gap=segment_distance(pa.position-ua,pa.position+ua,pb.position-ub,pb.position+ub)-a['radius_m']-b['radius_m']
        return gap,gap<=0,'exact_capsule'
    if ka==kb=='box':
        aa,bb=axes(pa),axes(pb)
        candidates=list(aa)+list(bb)+[u.cross(v) for u in aa for v in bb]
        delta=pb.position-pa.position
        gaps=[]
        for axis in candidates:
            norm=axis.norm()
            if norm<1e-10: continue
            u=axis*(1/norm)
            ra=sum(abs(u.dot(v))*h for v,h in zip(aa,a['half_extents_m']))
            rb=sum(abs(u.dot(v))*h for v,h in zip(bb,b['half_extents_m']))
            gaps.append(abs(delta.dot(u))-ra-rb)
        gap=max(gaps)
        # SAT is exact for overlap; separated clearance is a lower bound.
        return gap,gap<=1e-10,'obb_sat_distance_lower_bound'
    gap=aabb_gap(pa.position,extent(a,pa),pb.position,extent(b,pb))
    return gap,False,'enclosing_aabb_lower_bound'  # overlap is unresolved, never a proven hit


def sweep(a, pa0, pa1, b, pb0, pb1, margin=0.):
    """Earliest conservative contact fraction for translation over [0,1].

    Bounding sphere/swept AABB includes *all* orientations. margin must bound
    departure of either centre from its straight chord (caller supplies it).
    """
    if a['kind']==b['kind']=='sphere' and margin==0:
        p=pa0.position-pb0.position
        v=(pa1.position-pa0.position)-(pb1.position-pb0.position)
        r=a['radius_m']+b['radius_m']
        c=p.dot(p)-r*r
        if c<=0: return 0.,'exact_linear_sphere'
        aa,bb=v.dot(v),2*p.dot(v)
        disc=bb*bb-4*aa*c
        if aa==0 or bb>=0 or disc<0: return None,'exact_linear_sphere'
        t=(-bb-math.sqrt(disc))/(2*aa)
        return (t if 0<=t<=1 else None),'exact_linear_sphere'
    same_orientation=pa0.orientation==pa1.orientation and pb0.orientation==pb1.orientation
    exact=(a['kind']==b['kind']=='box' and same_orientation and
           pa0.orientation.array()==[1.,0.,0.,0.] and pb0.orientation.array()==[1.,0.,0.,0.] and margin==0)
    ea=extent(a,pa0) if same_orientation else V(*(radius(a),)*3)
    eb=extent(b,pb0) if same_orientation else V(*(radius(b),)*3)
    p=(pa0.position-pb0.position).array()
    v=((pa1.position-pa0.position)-(pb1.position-pb0.position)).array()
    size=[x+y+margin for x,y in zip(ea.array(),eb.array())]
    entry,exit=0.,1.
    for value,speed,half in zip(p,v,size):
        if abs(speed)<1e-14:
            if abs(value)>half: return None,'swept_aabb'
        else:
            t0,t1=sorted(((-half-value)/speed,(half-value)/speed))
            entry=max(entry,t0);exit=min(exit,t1)
            if entry>exit: return None,'swept_aabb'
    return entry,('exact_linear_aabb' if exact else 'conservative_swept_aabb')
