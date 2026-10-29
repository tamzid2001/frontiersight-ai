"""Catalog setup contract with a local provider fixture; never a real charge."""
import pytest
from scripts import configure_stripe as setup


def test_catalog_prices_coupon_and_webhook_match_the_offer(monkeypatch):
    calls=[]
    def request(method,path,form=None,**kwargs):
        calls.append((method,path,form,kwargs))
        if method=='GET':return {'data':[]}
        if path=='/products':return {'id':'prod_frontier'}
        if path=='/prices':return {'id':'price_'+form['recurring[interval]'],'active':True,'product':form['product'],'currency':'usd','unit_amount':form['unit_amount'],'recurring':{'interval':form['recurring[interval]']}}
        if path=='/coupons':return {'id':form['id'],'valid':True,'duration':form['duration'],'percent_off':form['percent_off']}
        if path=='/webhook_endpoints':return {'secret':'fixture-webhook-secret'}
        raise AssertionError(path)
    monkeypatch.setattr(setup,'_req',request)
    result=setup.configure('https://frontiersight-ai.vercel.app')
    assert result['PRICE_RESEARCHER_MONTHLY']=='price_month'
    assert result['PRICE_RESEARCHER_ANNUAL']=='price_year'
    assert result['STRIPE_WEBHOOK_SECRET']=='fixture-webhook-secret'
    prices=[c[2] for c in calls if c[0]=='POST' and c[1]=='/prices']
    assert {p['unit_amount'] for p in prices}=={1900,19000}
    assert all(c[1] not in ('/charges','/payment_intents','/subscriptions','/checkout/sessions') for c in calls)
    coupon=next(c[2] for c in calls if c[0]=='POST' and c[1]=='/coupons')
    assert coupon['percent_off']==50 and coupon['duration']=='once' and coupon['applies_to[products][0]']=='prod_frontier'
    with pytest.raises(ValueError):setup.configure('https://other.example')


def test_catalog_mismatch_stops_without_overwriting_prices(monkeypatch):
    calls=[]
    def request(method,path,*args,**kw):
        calls.append((method,path))
        if path.startswith('/products'):return {'data':[{'id':'prod_existing','metadata':{'application':'frontiersight-ai'}}]}
        return {'data':[{'id':'price_bad','active':True,'product':'prod_other','currency':'usd','unit_amount':1900,'recurring':{'interval':'month'}}]}
    monkeypatch.setattr(setup,'_req',request)
    with pytest.raises(ValueError):setup.configure('https://frontiersight-ai.vercel.app')
    assert all(method=='GET' for method,_ in calls)
