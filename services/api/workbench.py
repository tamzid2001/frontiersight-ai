"""Shared REST/MCP operations for authenticated workspaces and simulation edits.

The same scene document drives every view. Writes have version checks and durable
idempotency receipts. Model calls require authenticated paid access and a durable
reservation; an interrupted invocation is never automatically replayed.
"""
from __future__ import annotations
from dataclasses import replace
import base64
from datetime import datetime, timezone, timedelta
import hashlib
import io
import json
import os
import re
from urllib.parse import urlparse

from engine.scene_edit import validate_document, prepare_scene, fit_path
from engine.path_automation import plan_object_path, predict_track
from integrations.meta import spark, sam
from integrations.meta.path_edit import describe_paths
from integrations import clerk_billing
from services.api.clerk_auth import authenticate, Identity, WorkspaceError
from services.api.firestore_scenes import Scenes, _digest
from services.api.workspace_http import database


def actor(authorization):
    if authorization.startswith('Bearer fsa_'):
        from services.api.access_keys import verify
        identity = verify(database(), authorization)
        # A deleted/disabled Clerk user cannot keep acting with an old agent key.
        profile = clerk_billing._profile(identity.user_id)
        if getattr(profile, 'banned', False) or getattr(profile, 'locked', False):
            raise WorkspaceError(401,'account_unavailable')
    else:
        identity = authenticate(authorization)
    if clerk_billing.enabled() and not identity.org_id:
        identity = replace(identity, plan=clerk_billing.plan(identity.user_id))
    return identity


def library(identity, resource):
    return Scenes(database(), identity, os.environ.get('WORKSPACE_AUDIT_SECRET', ''), resource=resource)


def name(value):
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= 120:
        raise ValueError('name must be 1..120 characters')
    return value.strip()


def decode_frame(data):
    if not isinstance(data, str) or len(data) > 180000 or not re.match(r'^data:image/(png|jpeg);base64,', data):
        raise ValueError('frame requires a JPEG/PNG data URL, at most 180000 characters')
    try:
        raw = base64.b64decode(data.split(',', 1)[1], validate=True)
        from PIL import Image, UnidentifiedImageError
        with Image.open(io.BytesIO(raw)) as image:
            if image.format not in ('PNG', 'JPEG') or image.width * image.height > 4_000_000:
                raise ValueError('frame dimensions/format exceed the supported budget')
            width, height = image.size
            image.verify()
    except Exception:
        raise ValueError('frame is not a valid bounded JPEG/PNG image') from None
    return {'data_url': data, 'width': width, 'height': height, 'sha256': hashlib.sha256(raw).hexdigest()}


def media_payload(body):
    kind = body.get('kind')
    if kind == 'frame':
        frame = decode_frame(body.get('data_url'))
        from engine.path_automation import number
        return {**frame, 'kind': kind, 'timestamp_s': number(body.get('timestamp_s', 0), 'timestamp_s', 0, 86400),
                'source_video_id': body.get('source_video_id')}
    if kind == 'video':
        # Video bytes live in the provider's file service, not a Firestore JSON
        # document. Never fetch arbitrary client URLs with the server's identity.
        file_id = body.get('provider_file_id')
        if not isinstance(file_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{3,160}', file_id):
            raise ValueError('video requires a Meta provider_file_id')
        return {'kind': kind, 'provider': 'meta', 'provider_file_id': file_id,
                'source': 'USER_PROVIDED_REFERENCE', 'verification': 'provider checks access when invoked'}
    raise ValueError('media kind must be video or frame')


def use_object(scene, spec, object_id, x, y):
    document = validate_document(scene)
    spec = spark.validate_custom_object(spec)
    if not isinstance(object_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', object_id):
        raise ValueError('object_id must be 1..100 letters, digits, hyphens or underscores')
    if any(o.get('id', o.get('object_id')) == object_id for o in document['objects']):
        raise ValueError('object_id is already present')
    from engine.path_automation import xy
    point = xy([x, y], 'position')
    if fit_path([point], document['stage_metres'], spec['radius']) != [point]:
        raise ValueError('object does not fit at the requested position')
    category = spec['base_category']
    if category == 'object': category = 'robot'
    document['objects'].append({'id': object_id, 'category': category, 'waypoints': [point],
        'radius': spec['radius'], 'speed': 0 if category == 'shelf' else 1, 'delay': 0,
        'mode': 'stop', 'curve': 'straight', 'displayName': spec['name'], 'custom': {'spec': spec}})
    return {'scene': validate_document(document), 'persisted': False, 'source': 'USER_SAVED_OBJECT'}


def provider_key(store, identity, operation, key=None):
    """An encrypted per-workspace credential; raw values are never readable."""
    ref=store.root.collection('provider_keys').document('meta')
    if operation in ('save','delete'):
        if identity.token_scopes is not None or not identity.administrator:
            raise WorkspaceError(403,'clerk_workspace_admin_required')
        if identity.plan=='explorer':raise WorkspaceError(402,'researcher_plan_required')
    if operation=='delete':ref.delete(timeout=10);return {'configured':False}
    if operation in ('save','load'):
        secret=os.environ.get('BYOK_ENCRYPTION_KEY','').strip()
        if not secret:
            if operation=='save':raise WorkspaceError(503,'provider_key_encryption_not_configured')
        from cryptography.fernet import Fernet
        def fernet():
            try:return Fernet(secret.encode())
            except ValueError:return Fernet(base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest()))
    if operation=='save':
        if not isinstance(key,str) or not 20<=len(key)<=512 or any(c.isspace() for c in key):
            raise ValueError('invalid provider key')
        ref.set({'ciphertext':fernet().encrypt(key.encode()).decode(),'last4':key[-4:]},timeout=10)
        return {'configured':True,'last4':key[-4:]}
    record=ref.get(timeout=10).to_dict() or {}
    if operation=='load':
        if not record:return None
        if not secret:raise WorkspaceError(503,'provider_key_encryption_not_configured')
        try:return fernet().decrypt(record['ciphertext'].encode()).decode()
        except Exception:raise WorkspaceError(503,'provider_key_cannot_be_decrypted') from None
    return {'configured':bool(record),'last4':record.get('last4')}


class Workbench:
    def __init__(self, identity, *, stores=None):
        if not isinstance(identity, Identity):
            raise WorkspaceError(401, 'verified_identity_required')
        self.identity = identity
        self._stores = stores

    def store(self, kind):
        return self._stores[kind] if self._stores is not None else library(self.identity, kind)

    def model_call(self, operation, body, key, invoke):
        if self.identity.plan == 'explorer':
            raise WorkspaceError(402, 'researcher_plan_required_for_model_api')
        if not re.fullmatch(r'[A-Za-z0-9_-]{16,128}', key or ''):
            raise WorkspaceError(400, 'idempotency_key_required')
        store = self.store('scenes')
        # One reservation per key. No credential or media content is logged.
        receipt = store.root.collection('model_requests').document(_digest([self.identity.user_id, key]))
        digest = _digest({'operation': operation, 'body': body})
        now = datetime.now(timezone.utc)
        from google.cloud import firestore
        @firestore.transactional
        def reserve(tx):
            old = receipt.get(transaction=tx)
            if old.exists:
                record = old.to_dict()
                if record['digest'] != digest:
                    raise WorkspaceError(409, 'idempotency_key_reused')
                if record.get('status') == 'completed':
                    return json.loads(record['resultJson'])
                raise WorkspaceError(409, 'model_request_already_attempted_check_status')
            tx.create(receipt, {'digest': digest, 'status': 'running', 'operation': operation,
                               'createdAt': now, 'actorId': self.identity.user_id})
            return None
        cached = reserve(store.db.transaction(max_attempts=5))
        if cached is not None:
            return {**cached, 'replayed': True}
        try:
            from integrations.meta.credentials import using_key
            request_key = provider_key(store,self.identity,'load')
            if operation=='segment_video' and not request_key:
                raise WorkspaceError(403,'own_provider_key_required_for_video_file_access')
            with using_key(request_key):
                result = invoke()
            # Keep receipts bounded; segmentation can contain large masks.
            from services.api.firestore_scenes import validate_payload
            validate_payload(result)
            receipt.update({'status': 'completed', 'resultJson': json.dumps(result,allow_nan=False), 'completedAt': datetime.now(timezone.utc)})
            return {**result, 'replayed': False}
        except Exception:
            receipt.update({'status': 'failed_or_unknown', 'completedAt': datetime.now(timezone.utc)})
            raise

    def execute(self, operation, body, key=''):
        if not isinstance(body, dict):
            raise ValueError('request must be an object')
        if self.identity.token_scopes is not None:
            scope = ('model' if operation in ('generate_scene','generate_object','describe_paths','segment_frame','segment_video','propose_physics_profile')
                     else 'write' if operation.startswith(('create_','update_','delete_')) else 'read')
            if scope not in self.identity.token_scopes:
                raise WorkspaceError(403,'api_key_scope_denied')
        if len(json.dumps(body,allow_nan=False).encode())>350000:
            raise WorkspaceError(413,'request_body_budget_exceeded')
        from services.api.workbench_contract import validate_operation
        validate_operation(operation, body)
        if operation in ('get_profile','sync_profile','update_profile_preferences'):
            from services.api.profiles import Profiles
            profiles=Profiles(self.store('scenes').db,self.identity)
            if operation=='get_profile':return {'profile':profiles.get(),'siteId':'frontiersight-ai'}
            if operation=='sync_profile':
                if self.identity.token_scopes is not None:raise WorkspaceError(403,'clerk_session_required_for_profile_sync')
                from integrations.clerk_auth import verified_profile
                return {'profile':profiles.sync(verified_profile(self.identity.user_id)),'siteId':'frontiersight-ai'}
            return {'profile':profiles.preferences(body['preferences']),'siteId':'frontiersight-ai'}
        if operation == 'render_scene_frame':
            from engine.scene_media import render_frame
            return render_frame(body.get('scene'), body.get('timestamp_s',0),body.get('width',640),body.get('height',480))
        if operation == 'render_video_preview':
            from engine.scene_media import render_video_preview
            return render_video_preview(body.get('scene'),body.get('duration_s',4),body.get('fps',6),body.get('width',640),body.get('height',480))
        if operation == 'get_model_request':
            key = body.get('request_key')
            if not isinstance(key,str) or not re.fullmatch(r'[A-Za-z0-9_-]{16,128}',key): raise ValueError('invalid request key')
            row = self.store('scenes').root.collection('model_requests').document(_digest([self.identity.user_id,key])).get(timeout=10)
            if not row.exists: raise WorkspaceError(404,'model_request_not_found')
            data=row.to_dict()
            return {**{k:data[k] for k in ('status','operation') if k in data}, **({'result':json.loads(data['resultJson'])} if 'resultJson' in data else {})}
        if operation == 'plan_path':
            return plan_object_path(body.get('scene'), body.get('object_id'), body.get('goal'),
                resolution_m=body.get('resolution_m', .5), clearance_m=body.get('clearance_m', .1), smooth=body.get('smooth', True))
        if operation == 'predict_path':
            return predict_track(body.get('points'), horizon_s=body.get('horizon_s', 3), step_s=body.get('step_s', .25),
                space=body.get('space', 'world'), stage_metres=body.get('stage_metres'), radius=body.get('radius', 0))
        if operation == 'prepare_scene':
            return prepare_scene(body.get('scene'))
        if operation in ('generate_scene', 'generate_object', 'describe_paths', 'segment_frame', 'segment_video', 'propose_physics_profile'):
            def invoke():
                if operation == 'propose_physics_profile':
                    from integrations.meta.physics_edit import propose_physics
                    return propose_physics(body.get('profile'),body.get('description'),body.get('model'))
                if operation == 'generate_scene':
                    scene, meta = spark.generate_scene(body.get('description'), body.get('model'), body.get('candidates', 3))
                    # Assign stable IDs once; all later editors preserve them.
                    counts = {}
                    for obj in scene['objects']:
                        cat = obj['category']; counts[cat] = counts.get(cat, 0)+1; obj['id'] = f'{cat}-{counts[cat]}'
                    scene['stage_metres'] = [16, 14]
                    return {'scene': validate_document(scene), 'source': 'MODEL_DERIVED', 'model_call': meta}
                if operation == 'generate_object':
                    spec, meta = spark.design_custom_object(body.get('description'), body.get('model'))
                    return {'spec': spec, 'source': 'MODEL_DERIVED', 'model_call': meta}
                if operation == 'describe_paths':
                    return describe_paths(body.get('scene'), body.get('description'), body.get('model'))
                row = self.store('media').get(body.get('media_id'))
                media = row['payload']
                concept = body.get('concept', 'person')
                if operation == 'segment_frame':
                    if media.get('kind') != 'frame': raise ValueError('frame media required')
                    return sam.segment_image(media['data_url'], concept, timeout=25)
                if media.get('kind') != 'video': raise ValueError('video media required')
                return sam.segment_video(media['provider_file_id'], concept, is_file_id=True, timeout=25)
            self.store('scenes').consume_request(maximum=10)
            return self.model_call(operation, body, key, invoke)
        if operation == 'use_object':
            row = self.store('objects').get(body.get('object_record_id'))
            return use_object(body.get('scene'), row['payload']['spec'], body.get('object_id'), body.get('x'), body.get('y'))
        if operation == 'validate_object':
            return {'spec': spark.validate_custom_object(body.get('spec')), 'persisted': False}
        match = re.fullmatch(r'(list|get|create|update|delete)_(scenes|objects|media)', operation)
        if not match:
            raise WorkspaceError(404, 'operation_not_found')
        action, kind = match.groups()
        store = self.store(kind)
        store.consume_request()
        if action == 'list':
            limit = body.get('limit', 25)
            rows = store.list(limit=limit, after=body.get('after'))
            return {'items': rows, 'next': rows[-1]['id'] if len(rows) == limit else None, 'storage': 'firestore'}
        if action == 'get':
            return {'record': store.get(body.get('id')), 'storage': 'firestore'}
        clean = {k: body[k] for k in ('id', 'name', 'expectedVersion') if k in body}
        if action != 'delete':
            clean['name'] = name(body.get('name'))
            if kind == 'scenes':
                raw=body.get('scene')
                if isinstance(raw,dict) and raw.get('schema_version')=='frontiersight.project/1.0':
                    from engine.editor_document import validate_project
                    clean['payload']=validate_project(raw)
                elif isinstance(raw,dict) and raw.get('schema_version')=='2.0':
                    from engine.world3d import validate_scene as validate_3d
                    clean['payload']=validate_3d(raw)
                else: clean['payload'] = validate_document(raw)
                # Validate actual playback bounds; no silent repair on API saves.
                if clean['payload'].get('schema_version') not in ('2.0','frontiersight.project/1.0') and clean['payload']['objects']: prepare_scene(clean['payload'])
            elif kind == 'objects':
                clean['payload'] = {'spec': spark.validate_custom_object(body.get('spec'))}
            else:
                clean['payload'] = media_payload(body)
                parent = clean['payload'].get('source_video_id')
                if parent and store.get(parent)['payload'].get('kind') != 'video':
                    raise ValueError('source_video_id must reference a video in this workspace')
        return {**store.mutate(action, clean, key), 'storage': 'firestore'}
