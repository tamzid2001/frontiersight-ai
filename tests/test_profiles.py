import os
import uuid
import pytest
from services.api.clerk_auth import Identity,WorkspaceError
from services.api.profiles import Profiles
from services.api.firestore_scenes import client


def test_profile_owner_namespace_and_preference_authority():
    if not os.environ.get('FIRESTORE_EMULATOR_HOST'):pytest.skip('Firestore emulator required')
    database=client({'FIRESTORE_PROJECT_ID':'demo-quantura-web','FIRESTORE_EMULATOR_HOST':os.environ['FIRESTORE_EMULATOR_HOST']})
    identity=Identity('user_'+uuid.uuid4().hex,None,None,'researcher');profile=Profiles(database,identity)
    assert profile.get() is None
    result=profile.sync({'name':'Fixture User','email':'fixture@example.invalid'})
    assert result['siteId']=='frontiersight-ai' and result['clerkUserId']==identity.user_id
    result=profile.preferences({'timezone':'America/New_York','locale':'en-US','reducedMotion':True})
    assert result['email']=='fixture@example.invalid' and result['preferences']['reducedMotion']
    assert Profiles(database,Identity('user_other',None,None,'researcher')).get() is None
    for bad in ({'plan':'researcher'},{'email':'attacker@test.invalid'},{'timezone':'Unknown/Zone'},{'reducedMotion':1},{'locale':'<script>'}):
        with pytest.raises(ValueError):profile.preferences(bad)
    reader=Profiles(database,Identity(identity.user_id,None,None,'researcher',('read',)))
    with pytest.raises(WorkspaceError):reader.preferences({'locale':'en'})
    with pytest.raises(WorkspaceError):reader.sync({'name':'bad','email':'bad'})
    assert 'quantura_web/frontiersight-ai/userProfiles/' in profile.ref.path
    # Quantura data in another namespace is never read/overwritten.
    quantura=database.collection('quantura_profiles').document(identity.user_id);quantura.set({'unchanged':True})
    assert profile.get()['name']=='Fixture User' and quantura.get().to_dict()=={'unchanged':True}
    database.close()


def test_actual_account_endpoint_reads_only_frontier_firestore_profile(monkeypatch):
    if not os.environ.get('FIRESTORE_EMULATOR_HOST'):pytest.skip('Firestore emulator required')
    import threading,json,urllib.request,urllib.error
    from http.server import ThreadingHTTPServer
    from services.api import workbench_http,workspace_http,server,store
    database=client({'FIRESTORE_PROJECT_ID':'demo-quantura-web','FIRESTORE_EMULATOR_HOST':os.environ['FIRESTORE_EMULATOR_HOST']})
    identity=Identity('user_'+uuid.uuid4().hex,None,None,'researcher')
    Profiles(database,identity).sync({'name':'Frontier profile','email':'frontier@example.invalid'})
    monkeypatch.setenv('SCENE_STORE','firestore');monkeypatch.setattr(workbench_http,'actor',lambda _:identity)
    monkeypatch.setattr(workspace_http,'database',lambda:database)
    monkeypatch.setattr(store,'user_for_token',lambda _:(_ for _ in ()).throw(AssertionError('SQLite account read forbidden in Firestore mode')))
    monkeypatch.setattr(workbench_http.billing,'checkout_configuration',lambda:{'available':False})
    http=ThreadingHTTPServer(('127.0.0.1',0),server.H);thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
    try:
        for route in ('/api/me','/api/v1/account'):
            with urllib.request.urlopen('http://127.0.0.1:'+str(http.server_port)+route) as response:result=json.load(response)
            assert result['storage']=='firestore' and result['siteId']=='frontiersight-ai'
            assert result['profile']['name']=='Frontier profile' and result['profile']['clerkUserId']==identity.user_id
        assert result['plan']=='researcher'
        monkeypatch.setattr(workbench_http,'actor',lambda _:Identity(identity.user_id,None,None,'researcher',('model',)))
        try:urllib.request.urlopen('http://127.0.0.1:'+str(http.server_port)+'/api/me')
        except urllib.error.HTTPError as error:
            assert error.code==403;error.close()
        else:raise AssertionError('model-only key must not read profile PII')
    finally:http.shutdown();http.server_close();thread.join();database.close()
