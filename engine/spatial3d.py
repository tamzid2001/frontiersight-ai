"""SI/ENU spatial algebra. Quaternions use w,x,y,z; never Euler guesses."""
from __future__ import annotations

from dataclasses import dataclass
import math


def finite(value, name="number", low=-1e6, high=1e6):
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        raise ValueError(f"{name} must be a finite number")
    try:
        value = float(value)
    except OverflowError:
        raise ValueError(f"{name} exceeds its bound") from None
    if not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f"{name} outside [{low}, {high}]")
    return value


@dataclass(frozen=True)
class Vector3:
    x: float = 0.
    y: float = 0.
    z: float = 0.

    def __post_init__(self):
        for axis in ("x", "y", "z"):
            object.__setattr__(self, axis, finite(getattr(self, axis), axis, -1e12, 1e12))

    @classmethod
    def read(cls, value):
        if not isinstance(value, (list, tuple)) or len(value) != 3:
            raise ValueError("vector requires three SI components")
        return cls(*value)

    def array(self): return [self.x, self.y, self.z]
    def __add__(self, other): return Vector3(self.x+other.x, self.y+other.y, self.z+other.z)
    def __sub__(self, other): return Vector3(self.x-other.x, self.y-other.y, self.z-other.z)
    def __mul__(self, scale): return Vector3(self.x*scale, self.y*scale, self.z*scale)
    def dot(self, other): return self.x*other.x+self.y*other.y+self.z*other.z
    def cross(self, other): return Vector3(self.y*other.z-self.z*other.y, self.z*other.x-self.x*other.z, self.x*other.y-self.y*other.x)
    def norm(self): return math.sqrt(self.dot(self))


@dataclass(frozen=True)
class Quaternion:
    w: float = 1.
    x: float = 0.
    y: float = 0.
    z: float = 0.

    def __post_init__(self):
        values = [finite(v, "quaternion", -1, 1) for v in (self.w,self.x,self.y,self.z)]
        if abs(sum(v*v for v in values)-1) > 1e-6:
            raise ValueError("orientation must be a unit wxyz quaternion")

    @classmethod
    def read(cls, value):
        if not isinstance(value, (list, tuple)) or len(value) != 4:
            raise ValueError("orientation requires w,x,y,z")
        return cls(*value)

    def array(self): return [self.w,self.x,self.y,self.z]
    def inverse(self): return Quaternion(self.w,-self.x,-self.y,-self.z)
    def compose(self, other):
        a,b,c,d=self.w,self.x,self.y,self.z
        e,f,g,h=other.w,other.x,other.y,other.z
        values=[a*e-b*f-c*g-d*h,a*f+b*e+c*h-d*g,a*g-b*h+c*e+d*f,a*h+b*g-c*f+d*e]
        norm=math.sqrt(sum(v*v for v in values))
        return Quaternion(*(v/norm for v in values))

    def rotate(self, vector):
        q = Vector3(self.x,self.y,self.z)
        uv=q.cross(vector)
        return vector+uv*(2*self.w)+q.cross(uv)*2

    def advance(self, omega, dt):
        speed=omega.norm()
        if speed == 0: return self
        angle=speed*dt/2
        # Angular velocity is expressed in the body frame (right multiplication).
        return self.compose(Quaternion(math.cos(angle),*(v*math.sin(angle)/speed for v in omega.array())))


@dataclass(frozen=True)
class Pose3D:
    position: Vector3 = Vector3()
    orientation: Quaternion = Quaternion()

    def compose(self, local):
        return Pose3D(self.position+self.orientation.rotate(local.position),self.orientation.compose(local.orientation))

    def document(self):
        return {"position_m":self.position.array(),"orientation_wxyz":self.orientation.array()}


def segment_distance(a, b, c, d):
    """Closest distance of closed 3D segments, including degenerate segments."""
    u,v,w=b-a,d-c,a-c
    aa,bb,cc,dd,ee=u.dot(u),u.dot(v),v.dot(v),u.dot(w),v.dot(w)
    if aa <= 1e-16 and cc <= 1e-16: return w.norm()
    if aa <= 1e-16:
        s,t=0.,max(0.,min(1.,ee/cc))
    elif cc <= 1e-16:
        s,t=max(0.,min(1.,-dd/aa)),0.
    else:
        denominator=aa*cc-bb*bb
        s=max(0.,min(1.,(bb*ee-cc*dd)/denominator)) if denominator > 1e-16 else 0.
        t=(bb*s+ee)/cc
        if t < 0: t,s=0.,max(0.,min(1.,-dd/aa))
        elif t > 1: t,s=1.,max(0.,min(1.,(bb-dd)/aa))
    return (w+u*s-v*t).norm()
