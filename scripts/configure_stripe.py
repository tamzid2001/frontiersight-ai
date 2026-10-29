"""Explicit Stripe catalog/webhook setup. Never charges or emails a customer."""
import argparse
import json
import os
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from integrations.billing import _req


def configure(base):
    if base != 'https://frontiersight-ai.vercel.app':
        raise ValueError('review code before changing the deployment origin')
    products = _req('GET','/products?limit=100')['data']
    product = next((p for p in products if p.get('metadata',{}).get('application')=='frontiersight-ai'),None)
    if product is None:
        product = _req('POST','/products',{'name':'FrontierSight AI Researcher',
            'description':'Physical-world simulation workbench, saved scenes/objects and authenticated model API access.',
            'metadata[application]':'frontiersight-ai'},idempotency='frontiersight-researcher-product-v1')
    values={'BILLING_IDENTITY':'clerk','SCENE_STORE':'firestore'}
    for period,amount,interval in [('monthly',1900,'month'),('annual',19000,'year')]:
        lookup='frontiersight_researcher_'+period+'_usd_v1'
        prices=_req('GET','/prices?lookup_keys%5B%5D='+lookup)['data']
        price=prices[0] if prices else _req('POST','/prices',{'product':product['id'],'currency':'usd','unit_amount':amount,
            'recurring[interval]':interval,'lookup_key':lookup},idempotency=lookup)
        if (not price.get('active') or price.get('product')!=product['id'] or price.get('currency')!='usd'
            or price.get('unit_amount')!=amount or price.get('recurring',{}).get('interval')!=interval):
            raise ValueError('existing price differs from the displayed offer')
        values['PRICE_RESEARCHER_'+period.upper()]=price['id']
    coupons=_req('GET','/coupons?limit=100')['data']
    coupon=next((c for c in coupons if c.get('id')=='frontiersight_first_period_half_v1'),None)
    if coupon is None:
        coupon=_req('POST','/coupons',{'id':'frontiersight_first_period_half_v1','percent_off':50,'duration':'once',
            'name':'FrontierSight AI — first billing period 50% off','applies_to[products][0]':product['id']},idempotency='frontiersight_first_period_half_v1')
    if coupon.get('percent_off')!=50 or coupon.get('duration')!='once' or not coupon.get('valid'):
        raise ValueError('existing coupon differs from the advertised offer')
    values['STRIPE_FIRST_PERIOD_COUPON']=coupon['id']
    url=base+'/api/billing/webhook'
    endpoints=_req('GET','/webhook_endpoints?limit=100')['data']
    existing=next((x for x in endpoints if x.get('url')==url),None)
    if existing:
        raise ValueError('Webhook already exists: keep its securely stored signing secret; no duplicate endpoint was created.')
    hook=_req('POST','/webhook_endpoints',{'url':url,'enabled_events[]':[
        'checkout.session.completed','customer.subscription.created','customer.subscription.updated','customer.subscription.deleted'],
        'description':'FrontierSightAI stable Clerk billing identity'},idempotency='frontiersight-billing-webhook-v1')
    values['STRIPE_WEBHOOK_SECRET']=hook['secret']
    return values


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--apply',action='store_true');parser.add_argument('--out',type=Path,required=True);args=parser.parse_args()
    if not args.apply:parser.error('--apply is required; this creates Stripe catalog objects, not charges')
    if args.out.resolve().is_relative_to(Path(__file__).resolve().parents[1]):parser.error('private deployment output must be outside the Git checkout')
    if args.out.exists():parser.error('output already exists; choose a new private output path')
    values=configure('https://frontiersight-ai.vercel.app')
    descriptor=os.open(args.out,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(descriptor,'w') as stream:stream.write(''.join(k+'='+json.dumps(v)+'\n' for k,v in values.items()))
    print('Stripe catalog configured. Private deployment values saved; no customer charged or emailed.')

if __name__=='__main__':main()
