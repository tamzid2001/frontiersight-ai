"""FrontierSight-owned profiles in the shared project, never Quantura profiles.

Clerk is authoritative for identity/email/name. Client preferences cannot change
billing, org role, email, Clerk subject, tenant or plan. Server SDK access only.
"""
from datetime import datetime,timezone
import hashlib
import re
from zoneinfo import ZoneInfo,ZoneInfoNotFoundError
from .clerk_auth import Identity,WorkspaceError


class Profiles:
    def __init__(self,database,identity):
        if not isinstance(identity,Identity):raise WorkspaceError(401,'verified_identity_required')
        self.identity=identity
        self.ref=database.collection('quantura_web').document('frontiersight-ai').collection('userProfiles').document(hashlib.sha256(identity.user_id.encode()).hexdigest())

    def get(self):
        row=self.ref.get(timeout=10)
        if not row.exists:return None
        value=row.to_dict()
        if value.get('clerkUserId')!=self.identity.user_id:raise WorkspaceError(403,'profile_identity_mismatch')
        return value

    def sync(self,verified_profile):
        if self.identity.token_scopes is not None:raise WorkspaceError(403,'clerk_session_required_for_profile_sync')
        name=verified_profile.get('name','');email=verified_profile.get('email','')
        if not isinstance(name,str) or len(name)>240 or not isinstance(email,str) or len(email)>320:raise ValueError('invalid verified profile')
        self.ref.set({'siteId':'frontiersight-ai','clerkUserId':self.identity.user_id,'name':name,'email':email,
                      'updatedAt':datetime.now(timezone.utc).isoformat()},merge=True,timeout=10)
        return self.get()

    def preferences(self,value):
        if not isinstance(value,dict) or set(value)-{'timezone','locale','reducedMotion'}:raise ValueError('unsupported profile preference')
        if self.identity.token_scopes is not None and 'write' not in self.identity.token_scopes:raise WorkspaceError(403,'api_key_scope_denied')
        if 'timezone' in value:
            if not isinstance(value['timezone'],str) or len(value['timezone'])>80:raise ValueError('invalid timezone')
            try:ZoneInfo(value['timezone'])
            except (ZoneInfoNotFoundError,ValueError):raise ValueError('unknown timezone') from None
        if 'locale' in value and (not isinstance(value['locale'],str) or not re.fullmatch('[a-z]{2,3}(?:-[A-Za-z0-9]{2,8}){0,2}',value['locale'])):raise ValueError('invalid locale')
        if 'reducedMotion' in value and not isinstance(value['reducedMotion'],bool):raise ValueError('reducedMotion must be boolean')
        self.ref.set({'siteId':'frontiersight-ai','clerkUserId':self.identity.user_id,'preferences':value,
                      'updatedAt':datetime.now(timezone.utc).isoformat()},merge=True,timeout=10)
        return self.get()
