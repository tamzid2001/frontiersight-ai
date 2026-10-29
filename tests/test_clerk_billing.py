import hashlib
import hmac
import json
import time
from types import SimpleNamespace as NS
import pytest
from integrations import billing, clerk_billing as cb


@pytest.fixture
def provider(monkeypatch):
    settings={'BILLING_IDENTITY':'clerk','CLERK_SECRET_KEY':'sk_test_fixture','CLERK_ISSUER':'https://clerk.example',
      'CLERK_AUTHORIZED_PARTIES':'https://frontiersight.example','FIRESTORE_PROJECT_ID':'demo-project','FIRESTORE_USE_ADC':'true',
      'WORKSPACE_AUDIT_SECRET':'long-test-audit-secret-'*3,'STRIPE_SECRET_KEY':'sk_test_fixture',
      'STRIPE_WEBHOOK_SECRET':'whsec_fixture','PRICE_RESEARCHER_MONTHLY':'price_monthly',
      'PRICE_RESEARCHER_ANNUAL':'price_annual','APP_BASE_URL':'https://frontiersight.example'}
    for k,v in settings.items():monkeypatch.setenv(k,v)
    monkeypatch.delenv('VERCEL_ENV',raising=False)
    monkeypatch.delenv('STRIPE_FIRST_PERIOD_COUPON',raising=False)
    monkeypatch.setattr(cb,'_ensure_storage',lambda subject:None)
    profile=NS(private_metadata={},email_addresses=[NS(id='email_primary',email_address='buyer@example.com',verification=NS(status='verified'))],primary_email_address_id='email_primary')
    state={'rows':[],'calls':[],'profile':profile,'customer':{'id':'cus_fixture','metadata':{'application':'frontiersight-ai','clerk_subject':'user_buyer'}}}
    monkeypatch.setattr(cb,'_profile',lambda subject:profile)
    monkeypatch.setattr(cb,'_save_pointer',lambda subject,customer:profile.private_metadata.update(frontiersight_billing={'customer_id':customer}))
    def request(method,path,form=None,**kw):
        state['calls'].append((method,path,form,kw))
        if path=='/customers':return state['customer']
        if path.startswith('/customers/'):return state['customer']
        if path.startswith('/subscriptions?'):return {'data':state['rows'],'has_more':False}
        if path.startswith('/prices/'):
            annual=path.endswith('annual')
            return {'active':True,'currency':'usd','unit_amount':19000 if annual else 1900,'recurring':{'interval':'year' if annual else 'month','interval_count':1}}
        if path=='/checkout/sessions':return {'id':'cs_fixture','url':'https://checkout.stripe.com/c/pay/fixture'}
        if path=='/billing_portal/sessions':return {'url':'https://billing.stripe.com/p/session/fixture'}
        if path.startswith('/coupons/'):return {'valid':True,'duration':'once','percent_off':50}
        raise AssertionError(path)
    monkeypatch.setattr(billing,'_req',request)
    return state


def sub(**patch):
    return {'id':'sub_fixture','customer':'cus_fixture','status':'active','metadata':{'application':'frontiersight-ai','clerk_subject':'user_buyer'},
      'items':{'data':[{'price':{'id':'price_monthly'},'quantity':1}]},**patch}


def test_durable_pointer_checkout_and_authoritative_plan(provider):
    out=cb.checkout('user_buyer','monthly','checkout-idempotency-key')
    assert out['url'].startswith('https://checkout.stripe.com/')
    post=next(c for c in provider['calls'] if c[1]=='/checkout/sessions')
    assert post[2]['client_reference_id']=='user_buyer' and post[2]['customer']=='cus_fixture'
    assert post[2]['success_url'].startswith('https://frontiersight.example/') and post[3]['idempotency'].startswith('fs-checkout-')
    assert provider['profile'].private_metadata['frontiersight_billing']['customer_id']=='cus_fixture'
    assert cb.plan('user_buyer')=='explorer'
    provider['rows']=[sub()];assert cb.plan('user_buyer')=='researcher'
    assert cb.checkout('user_buyer','annual','another-checkout-key')['url'].startswith('https://billing.stripe.com/')
    for patch in [{'status':'past_due'},{'status':'canceled'},{'customer':'cus_other'},{'metadata':{'clerk_subject':'user_other','application':'frontiersight-ai'}},{'items':{'data':[{'price':{'id':'price_other'},'quantity':1}]}},{'items':{'data':[{'price':{'id':'price_monthly'},'quantity':2}]}}]:
        provider['rows']=[sub(**patch)];assert cb.plan('user_buyer')=='explorer'


def test_coupon_is_first_period_only_not_renewal_or_existing_customer(provider,monkeypatch):
    monkeypatch.setenv('STRIPE_FIRST_PERIOD_COUPON','coupon_first')
    cb.checkout('user_buyer','monthly','first-discount-checkout')
    first=next(c for c in provider['calls'] if c[1]=='/checkout/sessions')
    assert first[2]['discounts[0][coupon]']=='coupon_first'
    provider['calls'].clear();provider['rows']=[sub(status='canceled')]
    cb.checkout('user_buyer','annual','second-discount-checkout')
    later=next(c for c in provider['calls'] if c[1]=='/checkout/sessions');assert 'discounts[0][coupon]' not in later[2]
    assert later[2]['line_items[0][price]']=='price_annual'


def test_identity_and_config_failures_do_not_start_checkout(provider,monkeypatch):
    for period,key in [('bad','checkout-key-long-enough'),('monthly','short')]:
        with pytest.raises(ValueError):cb.checkout('user_buyer',period,key)
    with pytest.raises(ValueError):cb.portal('user_buyer')
    monkeypatch.delenv('STRIPE_WEBHOOK_SECRET');assert not billing.checkout_configuration()['ready']
    with pytest.raises(billing.BillingNotConfigured):cb.checkout('user_buyer','monthly','checkout-key-long-enough')
    monkeypatch.setenv('STRIPE_WEBHOOK_SECRET','whsec_fixture')
    provider['profile'].email_addresses[0].verification.status='unverified'
    with pytest.raises(ValueError):cb.customer_for('user_buyer',True)
    provider['profile'].private_metadata={'frontiersight_billing':{'customer_id':'../../other'}}
    with pytest.raises(ValueError):cb.customer_for('user_buyer')
    provider['profile'].private_metadata={'frontiersight_billing':{'customer_id':'cus_fixture'}}
    provider['customer']['metadata']['clerk_subject']='user_other'
    with pytest.raises(ValueError):cb.customer_for('user_buyer')


def test_webhooks_refetch_no_out_of_order_event_can_grant_a_plan(provider):
    cb.customer_for('user_buyer',True)
    provider['rows']=[sub(status='canceled')]
    event={'livemode':False,'type':'customer.subscription.created','data':{'object':sub()}}
    assert cb.webhook(event)=={'received':True}
    assert cb.webhook(event)=={'received':True} and cb.plan('user_buyer')=='explorer'
    with pytest.raises(ValueError):cb.webhook({**event,'livemode':True})
    assert cb.webhook({'livemode':False,'data':{'object':{}}})['ignored']
    event['data']['object']['customer']='cus_wrong'
    with pytest.raises(ValueError):cb.webhook(event)


def test_signature_rotation_accepts_any_valid_v1_and_rejects_duplicate_timestamps():
    raw=json.dumps({'type':'event'}).encode();ts=str(int(time.time()));secret='whsec_fixture'
    sig=hmac.new(secret.encode(),ts.encode()+b'.'+raw,hashlib.sha256).hexdigest()
    assert billing.verify_webhook(raw,'t='+ts+',v1=wrong,v1='+sig,secret)['type']=='event'
    for header in ['t='+ts+',t='+ts+',v1='+sig,'v1='+sig,'t='+ts+',v1=wrong']:
        with pytest.raises(ValueError):billing.verify_webhook(raw,header,secret)
    with pytest.raises(ValueError):billing.verify_webhook(b'x'*1_000_001,'t='+ts+',v1='+sig,secret)


def test_official_clerk_sdk_calls_use_private_metadata_and_bounded_timeouts(monkeypatch):
    import clerk_backend_api
    calls=[]
    class Users:
        def get(self,**kw):calls.append(('get',kw));return 'profile'
        def update_metadata(self,**kw):calls.append(('update',kw))
    class Client:
        def __init__(self,**kw):calls.append(('client',kw));self.users=Users()
        def __enter__(self):return self
        def __exit__(self,*a):pass
    monkeypatch.setattr(clerk_backend_api,'Clerk',Client)
    monkeypatch.setenv('CLERK_SECRET_KEY','fixture-key')
    assert cb._profile('user_test')=='profile'
    cb._save_pointer('user_test','cus_bound')
    assert calls[-1]==('update',{'user_id':'user_test','private_metadata':{'frontiersight_billing':{'customer_id':'cus_bound'}},'timeout_ms':5000})
    with pytest.raises(ValueError):cb._profile('../user')


def test_price_coupon_return_url_and_provider_response_fail_closed(provider,monkeypatch):
    original=billing._req
    def override(path_patch):
        monkeypatch.setattr(billing,'_req',lambda m,p,f=None,**kw:path_patch[p] if p in path_patch else original(m,p,f,**kw))
    monkeypatch.setenv('APP_BASE_URL','https://frontiersight.example/redirect?evil=1')
    with pytest.raises(billing.BillingNotConfigured):cb.checkout('user_buyer','monthly','bad-origin-checkout-key')
    monkeypatch.setenv('APP_BASE_URL','https://frontiersight.example')
    monkeypatch.setenv('STRIPE_FIRST_PERIOD_COUPON','coupon_first')
    override({'/coupons/coupon_first':{'valid':True,'percent_off':50,'duration':'forever'}})
    with pytest.raises(billing.BillingNotConfigured):cb.checkout('user_buyer','monthly','bad-coupon-checkout-key')
    monkeypatch.delenv('STRIPE_FIRST_PERIOD_COUPON')
    override({'/checkout/sessions':{'id':'cs_bad','url':'https://evil.example/'},'/billing_portal/sessions':{'url':'https://evil.example/'}})
    with pytest.raises(billing.BillingNotConfigured):cb.checkout('user_buyer','monthly','bad-result-checkout-key')
    with pytest.raises(billing.BillingNotConfigured):cb.portal('user_buyer')
    override({'/subscriptions?customer=cus_fixture&status=all&limit=100':{'data':[],'has_more':True}})
    with pytest.raises(billing.BillingNotConfigured):cb.subscriptions('cus_fixture')
    assert cb.subscriptions(None)==[]
