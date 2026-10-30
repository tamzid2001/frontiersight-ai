"""Real SDK tests: signed Clerk sessions and isolated local Firestore emulator."""
import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import os
import secrets
import time
import uuid

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import hashes, serialization
from services.api.clerk_auth import authenticate, Identity, WorkspaceError
from services.api.firestore_scenes import Scenes, client, validate_payload

@pytest.fixture()
def signed(monkeypatch):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    origin = 'https://frontiersight.example'
    issuer = 'https://test.clerk.accounts.dev'
    env = {'CLERK_SECRET_KEY': 'sk_test_' + secrets.token_urlsafe(32), 'CLERK_ISSUER': issuer,
           'CLERK_AUTHORIZED_PARTIES': origin,
           'CLERK_JWT_KEY': key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo).decode()}
    def token(**extra):
        now=int(time.time())
        claims={'v':2,'iss':issuer,'sub':'user_alice','sid':'sess_test','azp':origin,'iat':now-1,'nbf':now-1,'exp':now+60,'pla':'u:pro',**extra}
        enc=lambda obj:base64.urlsafe_b64encode(json.dumps(obj).encode()).rstrip(b'=')
        data=enc({'alg':'RS256','typ':'JWT','kid':'unit-test'})+b'.'+enc(claims)
        signature=key.sign(data,padding.PKCS1v15(),hashes.SHA256())
        return 'Bearer '+(data+b'.'+base64.urlsafe_b64encode(signature).rstrip(b'=')).decode()
    return env,token

def test_real_clerk_verification_and_active_entity_plans(signed):
    env,token=signed
    assert authenticate(token(),env).plan=='researcher'
    member=authenticate(token(o={'id':'org_acme','rol':'member'},pla='u:pro,o:free'),env)
    assert member.plan=='explorer' and not member.administrator
    assert member.tenant=='org_org_acme'
    admin=authenticate(token(o={'id':'org_acme','rol':'admin'},pla='o:pro'),env)
    assert admin.plan=='team' and admin.administrator
    for jwt in [token(exp=int(time.time())-60),token(azp='https://evil.example'),token(iss='https://wrong.example'),token(sub='../evil'),token(v=1)]:
        with pytest.raises(WorkspaceError) as error:authenticate(jwt,env)
        assert error.value.status==401

def test_auth_and_configuration_fail_closed(signed):
    env,token=signed
    with pytest.raises(WorkspaceError):authenticate('',env)
    with pytest.raises(WorkspaceError):authenticate(token(),{})
    with pytest.raises(WorkspaceError):authenticate(token(),{**env,'CLERK_AUTHORIZED_PARTIES':'https://host.example/path'})
    for settings in [{},{'FIRESTORE_PROJECT_ID':'real-project'},{'FIRESTORE_PROJECT_ID':'real-project','FIRESTORE_EMULATOR_HOST':'localhost:1234'},
                     {'FIRESTORE_PROJECT_ID':'demo-project','FIRESTORE_EMULATOR_HOST':'evil.example:80'},
                     {'FIRESTORE_PROJECT_ID':'demo-project','FIRESTORE_SERVICE_ACCOUNT_JSON':'bad json'}]:
        with pytest.raises(WorkspaceError):client(settings)
    with pytest.raises(WorkspaceError):Identity('../bad',None,None,'explorer')

def test_payload_limits_and_invalid_values():
    validate_payload({'workspace':{'objects':[{'x':1.0}]}})
    for value in [[],{'secret':float('nan')},{'constructor':'bad'},{'x':'z'*300000},{'x':object()}]:
        with pytest.raises(WorkspaceError):validate_payload(value)
    nested={};root=nested
    for _ in range(10):nested['x']={};nested=nested['x']
    with pytest.raises(WorkspaceError):validate_payload(root)

@pytest.fixture()
def database():
    if not os.environ.get('FIRESTORE_EMULATOR_HOST'):pytest.skip('Firestore emulator unavailable')
    db=client({'FIRESTORE_PROJECT_ID':'demo-quantura-web','FIRESTORE_EMULATOR_HOST':os.environ['FIRESTORE_EMULATOR_HOST']})
    yield db
    db.close()

def make_store(db,org=None,role=None):
    return Scenes(db,Identity('user_'+uuid.uuid4().hex,org,role,'researcher'),secrets.token_hex(32))

def test_actual_firestore_roundtrip_idempotency_version_and_delete(database):
    store=make_store(database)
    body={'name':'Physics review','payload':{'workspace':{'objects':[]}}};key=uuid.uuid4().hex
    row=store.mutate('create',body,key)
    assert store.mutate('create',body,key)['id']==row['id']
    assert len(store.list())==1
    assert store.list()[0]['payload']==body['payload']
    with pytest.raises(WorkspaceError):store.mutate('create',{**body,'name':'changed'},key)
    updated=store.mutate('update',{'id':row['id'],'name':'Reviewed','payload':{},'expectedVersion':1},uuid.uuid4().hex)
    assert updated['version']==2
    with pytest.raises(WorkspaceError):store.mutate('update',{'id':row['id'],'name':'Stale','payload':{},'expectedVersion':1},uuid.uuid4().hex)
    assert store.mutate('delete',{'id':row['id'],'expectedVersion':2},uuid.uuid4().hex)['deleted']
    assert store.list()==[]

def test_tenant_isolation_and_admin_delete(database):
    org='org_'+uuid.uuid4().hex
    owner=make_store(database,org,'org:admin');member=make_store(database,org,'org:member');outsider=make_store(database)
    row=owner.mutate('create',{'name':'Shared','payload':{}},uuid.uuid4().hex)
    assert member.list()[0]['id']==row['id']
    assert outsider.list()==[]
    with pytest.raises(WorkspaceError) as error:member.mutate('delete',{'id':row['id'],'expectedVersion':1},uuid.uuid4().hex)
    assert error.value.status==403
    with pytest.raises(WorkspaceError):outsider.mutate('delete',{'id':row['id'],'expectedVersion':1},uuid.uuid4().hex)

def test_concurrent_updates_have_one_winner_and_limits_are_real(database):
    store=make_store(database);store.maximum=1
    row=store.mutate('create',{'name':'One','payload':{}},uuid.uuid4().hex)
    with pytest.raises(WorkspaceError):store.mutate('create',{'name':'Two','payload':{}},uuid.uuid4().hex)
    def change(i):
        try:return store.mutate('update',{'id':row['id'],'name':str(i),'payload':{},'expectedVersion':1},uuid.uuid4().hex)
        except WorkspaceError as error:return error.code
    with ThreadPoolExecutor(2) as pool:results=list(pool.map(change,[1,2]))
    assert sum(isinstance(result,dict) for result in results)==1
    assert 'scene_version_conflict' in results
    store.consume_request(1)
    with pytest.raises(WorkspaceError) as error:store.consume_request(1)
    assert error.value.status==429

@pytest.fixture()
def http_service(signed, monkeypatch):
    if not os.environ.get('FIRESTORE_EMULATOR_HOST'):pytest.skip('Firestore emulator unavailable')
    from http.server import ThreadingHTTPServer
    from services.api.server import H
    from services.api import workspace_http
    import threading
    env,token=signed
    for k,v in {**env,'SCENE_STORE':'firestore','FIRESTORE_PROJECT_ID':'demo-quantura-web','WORKSPACE_AUDIT_SECRET':secrets.token_hex(32)}.items():monkeypatch.setenv(k,v)
    workspace_http.database.cache_clear()
    server=ThreadingHTTPServer(('127.0.0.1',0),H)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    yield f'http://127.0.0.1:{server.server_address[1]}',token
    server.shutdown();server.server_close();thread.join(timeout=3)
    workspace_http.database().close();workspace_http.database.cache_clear()

def test_http_clerk_firestore_integration_and_no_ephemeral_sql_fallback(http_service):
    import urllib.request,urllib.error
    base,token=http_service
    def call(path,body=None,authorization=None,headers=None):
        req=urllib.request.Request(base+path,data=None if body is None else json.dumps(body).encode(),
            headers={'Content-Type':'application/json',**({'Authorization':authorization} if authorization else {}),**(headers or {})})
        try:
            with urllib.request.urlopen(req,timeout=10) as r:return r.status,json.load(r)
        except urllib.error.HTTPError as error:return error.code,json.load(error)
    assert call('/api/auth/config')[1]['firestore_scenes_enabled'] is True
    assert call('/api/me')[1]['authenticated'] is False
    assert call('/api/scenes')[0]==401
    jwt=token(sub='user_http_'+uuid.uuid4().hex)
    assert call('/api/scene-context',authorization=jwt)[1]['storage']=='firestore'
    status,row=call('/api/scenes',{'name':'HTTP science','payload':{'workspace':{}}},jwt,{'Idempotency-Key':uuid.uuid4().hex})
    assert status==201 and row['version']==1
    assert call('/api/scenes',authorization=jwt)[1]['scenes'][0]['id']==row['id']
    assert call('/api/scenes?limit=101',authorization=jwt)[0]==400
    assert call('/api/scenes',authorization=jwt,headers={'Origin':'https://evil.example'})[0]==403
    assert call('/api/scenes',authorization=jwt,headers={'X-Workspace-Organization':'org_victim'})[0]==409
    assert call('/api/scenes/update',{'id':row['id'],'name':'Updated','payload':{},'expectedVersion':1},jwt,{'Idempotency-Key':uuid.uuid4().hex})[0]==200
    assert call('/api/scenes/delete',{'id':row['id'],'expectedVersion':2},jwt,{'Idempotency-Key':uuid.uuid4().hex})[0]==200
    assert call('/api/support',{'message':'hello'},jwt)[0]==401

def test_firestore_rejects_invalid_mutations_and_corrupt_state(database):
    store=make_store(database)
    with pytest.raises(WorkspaceError):Scenes(database,None,'x'*32)
    with pytest.raises(WorkspaceError):Scenes(database,store.identity,'short')
    for operation,body,key in [('invalid',{},uuid.uuid4().hex),('create',{'name':'x','payload':{},'org_id':'org_other'},uuid.uuid4().hex),
        ('create',{'name':'','payload':{}},uuid.uuid4().hex),('create',{'name':'x','payload':{}},'short'),
        ('update',{'id':'bad','name':'x','payload':{},'expectedVersion':1},uuid.uuid4().hex),
        ('delete',{'id':str(uuid.uuid4()),'expectedVersion':True},uuid.uuid4().hex)]:
        with pytest.raises(WorkspaceError):store.mutate(operation,body,key)
    with pytest.raises(WorkspaceError):store.list(101)
    with pytest.raises(WorkspaceError):store.list(1,'../../bad')
    row=store.mutate('create',{'name':'Cursor','payload':{}},uuid.uuid4().hex)
    assert store.list(1,row['id'])==[]
    store.mutations=1
    with pytest.raises(WorkspaceError) as error:store.mutate('create',{'name':'Over budget','payload':{}},uuid.uuid4().hex)
    assert error.value.code=='monthly_mutation_limit'
    store.root.set({'recordCount':-1},merge=True);store.mutations=100
    with pytest.raises(WorkspaceError) as error:store.mutate('create',{'name':'Corrupt','payload':{}},uuid.uuid4().hex)
    assert error.value.code=='invalid_workspace_state'

def test_misbound_emulator_and_wrong_project_credentials_are_rejected():
    for env in [{'FIRESTORE_PROJECT_ID':'demo-project','FIRESTORE_EMULATOR_HOST':'localhost:65534'},
        {'FIRESTORE_PROJECT_ID':'demo-project','FIRESTORE_SERVICE_ACCOUNT_JSON':json.dumps({'type':'service_account','project_id':'other-project'})},
        {'FIRESTORE_PROJECT_ID':'demo-project','FIRESTORE_SERVICE_ACCOUNT_JSON':json.dumps({'type':'service_account','project_id':'demo-project'})}]:
        with pytest.raises(WorkspaceError):client(env)

def test_http_rejects_malformed_bodies_methods_and_dependency_failures(http_service,monkeypatch):
    import httpx
    from services.api import workspace_http
    base,token=http_service
    headers={'Authorization':token(sub='user_errors_'+uuid.uuid4().hex),'Idempotency-Key':uuid.uuid4().hex}
    with httpx.Client(timeout=10) as transport:
        assert transport.get(base+'/api/scene-context',headers=headers).status_code==200
        assert transport.get(base+'/api/scenes?limit=not-a-number',headers=headers).status_code==400
        assert transport.get(base+'/api/scenes/update',headers=headers).status_code==405
        assert transport.post(base+'/api/scenes',headers=headers,content='not json').status_code==415
        assert transport.post(base+'/api/scenes',headers={**headers,'Content-Type':'application/json'},content='not json').status_code==400
        assert transport.post(base+'/api/scenes',headers={**headers,'Content-Type':'application/json'},content='x'*310000).status_code==413
        assert transport.post(base+'/api/scene-context',headers=headers,json={}).status_code==405
        with monkeypatch.context() as patch:
            def unavailable():raise RuntimeError('test-only-provider-details-should-not-leak')
            patch.setattr(workspace_http,'database',unavailable)
            response=transport.get(base+'/api/scenes',headers=headers)
            assert response.status_code==503 and 'provider-details' not in response.text


def test_local_contention_is_bounded_and_releases_after_failure():
    from services.api.firestore_scenes import _local_guard, _transaction_error
    from google.api_core.exceptions import Aborted
    with _local_guard('tenant-example'):
        with pytest.raises(WorkspaceError) as busy:
            with _local_guard('tenant-example',timeout=0):pass
        assert busy.value.status==429
    with pytest.raises(ValueError):
        with _local_guard('tenant-example'):raise ValueError('validation failed')
    with _local_guard('tenant-example',timeout=0):pass
    exhausted=ValueError('transaction failed');exhausted.__cause__=Aborted('lock timeout')
    with pytest.raises(WorkspaceError) as retry:_transaction_error(exhausted)
    assert retry.value.status==503
    with pytest.raises(ValueError):_transaction_error(ValueError('ordinary validation error'))
