"""Revocable personal-workspace agent keys. Only SHA-256 digests are stored."""
from datetime import datetime, timezone, timedelta
import hashlib
import re
import secrets
from services.api.clerk_auth import Identity, WorkspaceError
from google.cloud.firestore_v1.base_query import FieldFilter

SCOPES = {'read', 'write', 'model'}


def collection(database):
    return database.collection('quantura_web').document('frontiersight-ai').collection('api_keys')


def create(database, identity, name, scopes, days):
    if identity.org_id or identity.token_scopes is not None:
        raise WorkspaceError(403, 'personal_clerk_session_required_to_manage_keys')
    if not isinstance(name,str) or not 1<=len(name.strip())<=80:
        raise ValueError('key name must be 1..80 characters')
    if not isinstance(scopes,list) or not scopes or len(scopes)!=len(set(scopes)) or not set(scopes)<=SCOPES:
        raise ValueError('choose distinct read, write and/or model scopes')
    if type(days) is not int or not 1<=days<=90:
        raise ValueError('key lifetime must be 1..90 days')
    # Keep key creation bounded. Revoked/expired records are retained for audit;
    # only active keys count, without requiring a composite Firestore index.
    now=datetime.now(timezone.utc)
    rows=collection(database).where(filter=FieldFilter('user_id','==',identity.user_id)).limit(101).stream(timeout=10)
    records=[row.to_dict() for row in rows]
    if len(records)>100 or sum(not x.get('revoked') and x['expiresAt']>now for x in records)>=10:
        raise WorkspaceError(429,'api_key_limit')
    token='fsa_'+secrets.token_urlsafe(40)
    digest=hashlib.sha256(token.encode()).hexdigest()
    expiry=now+timedelta(days=days)
    collection(database).document(digest).create({'user_id':identity.user_id,'name':name.strip(),
        'prefix':token[:10],'scopes':scopes,'createdAt':now,'expiresAt':expiry,'revoked':False},timeout=10)
    return {'key':token,'id':digest,'prefix':token[:10],'scopes':scopes,'expiresAt':expiry.isoformat(),
            'warning':'Shown once. Save securely; never place it in a URL or public client bundle.'}


def verify(database, authorization):
    if not re.fullmatch(r'Bearer fsa_[A-Za-z0-9_-]{54}',authorization or ''):
        raise WorkspaceError(401,'invalid_api_key')
    token=authorization[7:]
    row=collection(database).document(hashlib.sha256(token.encode()).hexdigest()).get(timeout=10)
    data=row.to_dict() or {}
    if not row.exists or data.get('revoked') or data.get('expiresAt',datetime.min.replace(tzinfo=timezone.utc))<=datetime.now(timezone.utc):
        raise WorkspaceError(401,'expired_or_revoked_api_key')
    scopes=data.get('scopes')
    if not isinstance(scopes,list) or not scopes or not set(scopes)<=SCOPES:
        raise WorkspaceError(401,'invalid_api_key_scope')
    return Identity(data['user_id'],None,None,'explorer',tuple(scopes))


def manage(database, identity, key_id=None):
    if identity.org_id or identity.token_scopes is not None:
        raise WorkspaceError(403,'personal_clerk_session_required_to_manage_keys')
    if key_id is None:
        rows=collection(database).where(filter=FieldFilter('user_id','==',identity.user_id)).limit(100).stream(timeout=10)
        return {'keys':[{'id':row.id,**{k:v.isoformat() if isinstance(v,datetime) else v for k,v in row.to_dict().items() if k!='user_id'}} for row in rows]}
    if not isinstance(key_id,str) or not re.fullmatch(r'[a-f0-9]{64}',key_id):
        raise ValueError('invalid key id')
    ref=collection(database).document(key_id);row=ref.get(timeout=10)
    if not row.exists or row.to_dict().get('user_id')!=identity.user_id:
        raise WorkspaceError(404,'api_key_not_found')
    ref.update({'revoked':True},timeout=10)
    return {'revoked':True,'id':key_id}
