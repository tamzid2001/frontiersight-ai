"""Bounded JSON HTTP adapter for the shared authenticated workbench operations."""
from __future__ import annotations
import json
import os
from urllib.parse import urlparse, parse_qs
from integrations import billing, clerk_billing
from integrations.meta.spark import BlockedCredentials, ModelError
from services.api.clerk_auth import WorkspaceError
from services.api.workbench import actor, Workbench

ROUTES = {
    '/api/v1/profile/get':'get_profile','/api/v1/profile/sync':'sync_profile','/api/v1/profile/preferences':'update_profile_preferences',
    '/api/v1/physics/propose':'propose_physics_profile',
    '/api/v1/media/render-frame':'render_scene_frame', '/api/v1/media/render-preview':'render_video_preview',
    '/api/v1/model-requests/get':'get_model_request',
    '/api/v1/paths/plan': 'plan_path', '/api/v1/paths/predict': 'predict_path',
    '/api/v1/paths/describe': 'describe_paths', '/api/v1/scenes/prepare': 'prepare_scene',
    '/api/v1/scenes/generate': 'generate_scene', '/api/v1/objects/generate': 'generate_object',
    '/api/v1/objects/validate': 'validate_object', '/api/v1/objects/use': 'use_object',
    '/api/v1/media/segment-frame': 'segment_frame', '/api/v1/media/segment-video': 'segment_video',
}
for kind in ('scenes', 'objects', 'media'):
    for action in ('list', 'get', 'create', 'update', 'delete'):
        ROUTES[f'/api/v1/{kind}/{action}'] = f'{action}_{kind}'


def check_origin(handler):
    origin = handler.headers.get('Origin')
    allowed = [s.strip() for s in os.environ.get('CLERK_AUTHORIZED_PARTIES', os.environ.get('APP_BASE_URL', 'https://frontiersight-ai.vercel.app')).split(',')]
    if origin and origin not in allowed:
        raise WorkspaceError(403, 'request_origin_not_allowed')


def body(handler, maximum=350000):
    try: length = int(handler.headers.get('Content-Length', '0'))
    except ValueError: raise WorkspaceError(400, 'invalid_content_length') from None
    if not 0 < length <= maximum:
        raise WorkspaceError(413, 'request_body_budget_exceeded')
    if not handler.headers.get('Content-Type', '').lower().startswith('application/json'):
        raise WorkspaceError(415, 'json_required')
    value = handler._body()
    if not isinstance(value, dict): raise WorkspaceError(400, 'json_object_required')
    return value


def handle(handler, route, method):
    account_alias=route=='/api/me' and os.environ.get('SCENE_STORE')=='firestore'
    legacy_billing = clerk_billing.enabled() and route in ('/api/billing/checkout', '/api/billing/portal', '/api/billing/webhook')
    public_path = route in ('/api/paths/plan', '/api/paths/predict')
    if public_path:
        try:
            check_origin(handler)
            if method != 'POST': raise WorkspaceError(405, 'post_required')
            request = body(handler)
            from engine.path_automation import plan_object_path, predict_track
            if route.endswith('plan'):
                result = plan_object_path(request.get('scene'), request.get('object_id'), request.get('goal'),
                    resolution_m=request.get('resolution_m', .5),clearance_m=request.get('clearance_m', .1),smooth=request.get('smooth', True))
            else:
                result = predict_track(request.get('points'),horizon_s=request.get('horizon_s',3),step_s=request.get('step_s',.25),
                    space=request.get('space','world'),stage_metres=request.get('stage_metres'),radius=request.get('radius',0))
            handler._send(200,result)
        except WorkspaceError as error: handler._send(error.status,{'error':error.code})
        except (ValueError, TypeError, OverflowError): handler._send(400,{'error':'invalid_path_request'})
        return True
    if not route.startswith('/api/v1/') and not legacy_billing and not account_alias:
        return False
    try:
        check_origin(handler)
        if route == '/api/billing/webhook':
            length = int(handler.headers.get('Content-Length', '0'))
            if not 0 < length <= 1_000_000: raise WorkspaceError(413, 'webhook_budget_exceeded')
            event = billing.verify_webhook(handler.rfile.read(length), handler.headers.get('Stripe-Signature', ''))
            handler._send(200, clerk_billing.webhook(event)); return True
        if route not in ROUTES and route not in ('/api/v1/account', '/api/v1/billing/checkout', '/api/v1/billing/portal', '/api/v1/keys/create', '/api/v1/keys/list', '/api/v1/keys/revoke', '/api/v1/provider-key/save', '/api/v1/provider-key/status', '/api/v1/provider-key/delete') and not legacy_billing and not account_alias:
            raise WorkspaceError(404, 'route_not_found')
        if route == '/api/v1/account' or account_alias:
            if method != 'GET': raise WorkspaceError(405, 'get_required')
        elif method != 'POST':
            raise WorkspaceError(405, 'post_required')
        identity = actor(handler.headers.get('Authorization', ''))
        org = handler.headers.get('X-Workspace-Organization')
        if org is not None and org != (identity.org_id or 'personal'):
            raise WorkspaceError(409, 'session_workspace_changed')
        if route == '/api/v1/account' or account_alias:
            if identity.token_scopes is not None and 'read' not in identity.token_scopes:raise WorkspaceError(403,'api_key_scope_denied')
            from services.api.profiles import Profiles
            from services.api.workspace_http import database,enabled
            profile=Profiles(database(),identity).get() if enabled() else None
            common={'userId':identity.user_id,'orgId':identity.org_id,'orgRole':identity.org_role,
                    'plan':identity.plan,'profile':profile,'siteId':'frontiersight-ai',
                    'storage':'firestore' if enabled() else 'unavailable','billing':billing.checkout_configuration()}
            if account_alias:
                common.update(user={'id':identity.user_id,'clerk_id':identity.user_id,'name':(profile or {}).get('name',''),
                                    'email':(profile or {}).get('email','')},entitlements=billing.entitlements(identity.plan))
            handler._send(200,common)
            return True
        request = body(handler)
        if route.startswith('/api/v1/provider-key/'):
            from services.api.workbench import provider_key, library
            result=provider_key(library(identity,'scenes'),identity,route.rsplit('/',1)[1],request.get('key'))
        elif route.startswith('/api/v1/keys/'):
            from services.api import access_keys
            from services.api.workspace_http import database
            if route.endswith('create'):
                result = access_keys.create(database(),identity,request.get('name'),request.get('scopes'),request.get('days',30))
            else:
                result = access_keys.manage(database(),identity,request.get('id') if route.endswith('revoke') else None)
        elif route.endswith('/billing/checkout') or route.endswith('/billing/portal'):
            if not clerk_billing.enabled(): raise billing.BillingNotConfigured('Clerk billing is not configured. No payment was taken.')
            if identity.token_scopes is not None: raise WorkspaceError(403,'clerk_session_required_for_billing')
            if identity.org_id: raise WorkspaceError(409, 'switch_to_personal_workspace_for_individual_subscription')
            result = (clerk_billing.checkout(identity.user_id, request.get('period', 'monthly'), handler.headers.get('Idempotency-Key', ''))
                      if route.endswith('checkout') else clerk_billing.portal(identity.user_id))
        else:
            result = Workbench(identity).execute(ROUTES[route], request, handler.headers.get('Idempotency-Key', ''))
        handler._send(200, result)
    except WorkspaceError as error:
        handler._send(error.status, {'error': error.code})
    except billing.BillingNotConfigured:
        handler._send(503, {'error': 'Stripe Checkout is not configured. No payment was taken.', 'code': 'BILLING_NOT_CONFIGURED'})
    except BlockedCredentials:
        handler._send(503, {'error': 'model_provider_not_configured'})
    except ModelError:
        handler._send(502, {'error': 'model_request_failed_scene_unchanged'})
    except (ValueError, TypeError, KeyError, OverflowError):
        handler._send(400, {'error': 'invalid_workbench_request'})
    except Exception:
        handler._send(503, {'error': 'workbench_service_unavailable'})
    return True
