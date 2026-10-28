"""Exercise billing availability and real Stripe request construction offline."""
import pytest
from integrations import billing


def configure(monkeypatch, production=False):
    monkeypatch.delenv('VERCEL',raising=False)
    monkeypatch.setenv('VERCEL_ENV','production' if production else 'development')
    monkeypatch.setenv('STRIPE_SECRET_KEY','sk_live_fixture' if production else 'sk_test_fixture')
    monkeypatch.setenv('STRIPE_WEBHOOK_SECRET','whsec_fixture')
    monkeypatch.setenv('PRICE_RESEARCHER_MONTHLY','price_monthly_fixture')
    monkeypatch.setenv('PRICE_RESEARCHER_ANNUAL','price_annual_fixture')


def test_public_config_never_exposes_credentials_and_distinguishes_periods(monkeypatch):
    configure(monkeypatch)
    result=billing.checkout_configuration()
    assert result['ready'] and result['mode']=='test'
    assert result['monthly_usd']==19 and result['annual_usd']==190
    assert 'fixture' not in str(result)
    monkeypatch.delenv('PRICE_RESEARCHER_ANNUAL')
    assert billing.checkout_configuration()['periods']=={'monthly':True,'annual':False}


def test_production_fails_closed_on_test_keys_and_ephemeral_vercel_store(monkeypatch):
    configure(monkeypatch,True)
    assert billing.checkout_configuration()['mode']=='live'
    monkeypatch.setenv('VERCEL','1')
    assert not billing.checkout_configuration()['ready']
    with pytest.raises(billing.BillingNotConfigured):
        billing.create_checkout({'id':1,'email':'test@example.com'},'price_monthly_fixture','https://example.com/success','https://example.com/cancel')
    monkeypatch.delenv('VERCEL')
    monkeypatch.setenv('STRIPE_SECRET_KEY','sk_test_fixture')
    assert not billing.checkout_configuration()['ready']
    monkeypatch.delenv('STRIPE_WEBHOOK_SECRET')
    assert not billing.checkout_configuration()['ready']


@pytest.mark.parametrize('period,amount,interval',[('monthly',1900,'month'),('annual',19000,'year')])
def test_checkout_verifies_amount_currency_and_period_before_session(monkeypatch,period,amount,interval):
    configure(monkeypatch)
    calls=[]
    def request(method,path,form=None):
        calls.append((method,path,form))
        if method=='GET':return {'active':True,'currency':'usd','unit_amount':amount,'recurring':{'interval':interval,'interval_count':1}}
        return {'id':'cs_fixture','url':'https://checkout.stripe.com/fixture'}
    monkeypatch.setattr(billing,'_req',request)
    result=billing.create_checkout({'id':7,'email':'buyer@example.com'},f'price_{period}_fixture','https://example.com/success','https://example.com/cancel',period)
    assert result['id']=='cs_fixture' and len(calls)==2
    assert calls[1][2]['line_items[0][price]']==f'price_{period}_fixture'
    assert calls[1][2]['subscription_data[metadata][user_id]']=='7'
    assert calls[1][2]['mode']=='subscription'


@pytest.mark.parametrize('patch',[{'active':False},{'currency':'eur'},{'unit_amount':1},{'recurring':{'interval':'year','interval_count':1}},{'recurring':{'interval':'month','interval_count':2}}])
def test_mismatched_stripe_price_never_creates_checkout(monkeypatch,patch):
    configure(monkeypatch)
    calls=[]
    def request(method,path,form=None):
        calls.append(method)
        return {'active':True,'currency':'usd','unit_amount':1900,'recurring':{'interval':'month','interval_count':1}}|patch
    monkeypatch.setattr(billing,'_req',request)
    with pytest.raises(billing.BillingNotConfigured):
        billing.create_checkout({'id':1,'email':'buyer@example.com'},'price_monthly_fixture','https://example.com/success','https://example.com/cancel')
    assert calls==['GET']
    with pytest.raises(ValueError):billing.create_checkout({},'', '', '', 'invalid')
    with pytest.raises(billing.BillingNotConfigured):billing.create_checkout({},'price_unknown','','')


@pytest.mark.parametrize('patch',[{'livemode':False},{'livemode':True}])
def test_production_price_must_be_live(monkeypatch,patch):
    configure(monkeypatch,True)
    monkeypatch.delenv('DATABASE_URL',raising=False)
    calls=[]
    def request(method,path,form=None):
        calls.append(method)
        return ({'active':True,'currency':'usd','unit_amount':1900,'recurring':{'interval':'month','interval_count':1}}|patch) if method=='GET' else {'id':'fixture'}
    monkeypatch.setattr(billing,'_req',request)
    if patch['livemode']:
        assert billing.create_checkout({'id':1,'email':'x@example.com'},'price_monthly_fixture','','')['id']=='fixture'
        assert calls==['GET','POST']
    else:
        with pytest.raises(billing.BillingNotConfigured):billing.create_checkout({},'price_monthly_fixture','','')
        assert calls==['GET']
    monkeypatch.setenv('DATABASE_URL','postgresql://unsupported.invalid/db')
    assert billing.checkout_configuration()['ready'] is False


def test_actual_http_checkout_and_portal_adapter_against_local_provider(monkeypatch):
    import json,threading,urllib.parse
    from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
    configure(monkeypatch)
    monkeypatch.delenv('DATABASE_URL',raising=False)
    observed=[]
    class Provider(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            observed.append((self.command,self.path,self.headers.get('Authorization')))
            if self.path!='/prices/price_monthly_fixture':
                self.send_response(404);self.end_headers();self.wfile.write(b'{"error":"not found"}');return
            self.send_response(200);self.end_headers();self.wfile.write(json.dumps({'active':True,'currency':'usd','unit_amount':1900,'recurring':{'interval':'month','interval_count':1}}).encode())
        def do_POST(self):
            form=urllib.parse.parse_qs(self.rfile.read(int(self.headers['Content-Length'])).decode())
            observed.append((self.command,self.path,form))
            self.send_response(200);self.end_headers();self.wfile.write(b'{"id":"cs_local","url":"https://checkout.stripe.com/local-fixture"}')
    server=ThreadingHTTPServer(('127.0.0.1',0),Provider);worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
    monkeypatch.setattr(billing,'API',f'http://127.0.0.1:{server.server_port}')
    try:
        assert billing.create_checkout({'id':7,'email':'buyer@example.com'},'price_monthly_fixture','https://example.com/success','https://example.com/cancel')['id']=='cs_local'
        assert observed[0][2]=='Bearer sk_test_fixture'
        assert observed[1][2]['line_items[0][price]']==['price_monthly_fixture']
        assert observed[1][2]['client_reference_id']==['7']
        assert billing.create_portal('cus_fixture','https://example.com')['url'].startswith('https://checkout.stripe.com/')
        assert observed[-1][2]['customer']==['cus_fixture']
        with pytest.raises(RuntimeError,match='404'):billing._req('GET','/missing')
        monkeypatch.delenv('STRIPE_SECRET_KEY')
        with pytest.raises(billing.BillingNotConfigured):billing._req('GET','/missing')
    finally:
        server.shutdown();server.server_close();worker.join(timeout=3)


def test_webhook_rejects_missing_expired_and_forged_signatures():
    import time
    with pytest.raises(billing.BillingNotConfigured):billing.verify_webhook(b'{}','',secret='')
    for header in ('junk',f't={int(time.time())-1000},v1=bad',f't={int(time.time())},v1=bad'):
        with pytest.raises(ValueError):billing.verify_webhook(b'{}',header,secret='whsec_fixture')
