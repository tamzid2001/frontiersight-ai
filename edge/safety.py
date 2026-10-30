"""Advisory-only validity checks. Not a certified physical safety controller."""
import math
from engine.spatial3d import finite,Vector3 as V


def validate_recommendation(recommendation,health,*,now_s,max_speed_mps=1.,max_age_s=1.):
    if health.get('mode') not in ('SHADOW','ADVISORY'):return {'accepted':False,'reason':'mode_not_advisory','actuation':False}
    if health.get('mode')=='SHADOW':return {'accepted':False,'reason':'shadow_never_commands','actuation':False}
    now=finite(now_s,'now',0,1e12);age=now-finite(health.get('observed_at_s'),'observed_at_s',0,1e12)
    if not health.get('connected') or not 0<=age<=max_age_s:return {'accepted':False,'reason':'stale_or_disconnected','actuation':False}
    if health.get('independent_interlock_ok') is not True:return {'accepted':False,'reason':'independent_interlock_not_confirmed','actuation':False}
    if not isinstance(recommendation,dict) or set(recommendation)-{'velocity_mps','expires_at_s','object_id'}:raise ValueError('invalid recommendation')
    expiry=finite(recommendation.get('expires_at_s'),'expiry',0,1e12)
    speed=V.read(recommendation.get('velocity_mps')).norm()
    if not now<expiry<=now+1:return {'accepted':False,'reason':'invalid_recommendation_ttl','actuation':False}
    if speed>max_speed_mps:return {'accepted':False,'reason':'speed_envelope','actuation':False}
    return {'accepted':True,'reason':'advisory_only_external_controller_must_independently_validate','actuation':False,'recommendation':recommendation}
