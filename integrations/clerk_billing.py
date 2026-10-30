"""Clerk subject -> Stripe customer: durable billing, independent of local SQLite.

Private Clerk metadata holds only a customer pointer. Stripe remains authoritative
for active subscriptions. Redirects and plan claims cannot grant an entitlement.
"""
from __future__ import annotations
import hashlib
import os
import re
from urllib.parse import urlencode, urlparse
from . import billing

PRODUCT = 'frontiersight-ai'


def enabled():
    return os.environ.get('BILLING_IDENTITY') == 'clerk'


def _profile(subject):
    if not re.fullmatch(r'user_[A-Za-z0-9_-]{1,120}', subject):
        raise ValueError('verified Clerk subject required')
    from clerk_backend_api import Clerk
    with Clerk(bearer_auth=os.environ['CLERK_SECRET_KEY'], timeout_ms=5000) as client:
        return client.users.get(user_id=subject, timeout_ms=5000)


def _save_pointer(subject, customer):
    from clerk_backend_api import Clerk
    with Clerk(bearer_auth=os.environ['CLERK_SECRET_KEY'], timeout_ms=5000) as client:
        client.users.update_metadata(user_id=subject,
            private_metadata={'frontiersight_billing': {'customer_id': customer}}, timeout_ms=5000)


def customer_for(subject, create=False):
    profile = _profile(subject)
    pointer = (profile.private_metadata or {}).get('frontiersight_billing') or {}
    customer = pointer.get('customer_id') if isinstance(pointer, dict) else None
    if customer:
        if not re.fullmatch(r'cus_[A-Za-z0-9]+', customer):
            raise ValueError('invalid billing identity')
        record = billing._req('GET', '/customers/' + customer)
        if record.get('deleted') or record.get('metadata', {}).get('clerk_subject') != subject or record.get('metadata', {}).get('application') != PRODUCT:
            raise ValueError('billing identity mismatch')
        return customer
    if not create:
        return None
    emails = profile.email_addresses or []
    email = next((e.email_address for e in emails if e.id == profile.primary_email_address_id
                  and e.verification and e.verification.status == 'verified'), None)
    if not email:
        raise ValueError('verify your primary email before subscribing')
    record = billing._req('POST', '/customers', {'email': email,
        'metadata[clerk_subject]': subject, 'metadata[application]': PRODUCT},
        idempotency='fs-customer-' + hashlib.sha256(subject.encode()).hexdigest())
    customer = record['id']
    _save_pointer(subject, customer)
    return customer


def subscriptions(customer):
    if not customer:
        return []
    result = billing._req('GET', '/subscriptions?' + urlencode({'customer': customer, 'status': 'all', 'limit': 100}))
    if result.get('has_more'):
        raise billing.BillingNotConfigured('Subscription history requires support review.')
    return result.get('data', [])


def paid_subscription(subject, customer, rows):
    prices = {os.environ.get('PRICE_RESEARCHER_MONTHLY'), os.environ.get('PRICE_RESEARCHER_ANNUAL')} - {None, ''}
    for row in rows:
        meta = row.get('metadata') or {}
        items = (row.get('items') or {}).get('data') or []
        if (row.get('customer') == customer and row.get('status') in ('active', 'trialing')
            and meta.get('clerk_subject') == subject and meta.get('application') == PRODUCT
            and len(items) == 1 and items[0].get('quantity') == 1
            and items[0].get('price', {}).get('id') in prices):
            return row
    return None


def plan(subject):
    customer = customer_for(subject)
    return 'researcher' if paid_subscription(subject, customer, subscriptions(customer)) else 'explorer'


def _base():
    value = os.environ.get('APP_BASE_URL', 'https://frontiersight-ai.vercel.app').rstrip('/')
    parsed = urlparse(value)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.path or parsed.query or parsed.fragment or parsed.username:
        raise billing.BillingNotConfigured('Invalid billing return origin.')
    return value


def _ensure_storage(subject):
    # Verify a real durable read/write before a customer can pay for saved work.
    # The transaction is a small quota record, never a synthetic paid grant.
    from services.api.clerk_auth import Identity
    from services.api.firestore_scenes import Scenes, client
    database = client()
    try:
        Scenes(database, Identity(subject,None,None,'explorer'),
               os.environ.get('WORKSPACE_AUDIT_SECRET','')).consume_request(maximum=5)
    finally:
        database.close()


def checkout(subject, period, key):
    if period not in ('monthly', 'annual'):
        raise ValueError('period must be monthly or annual')
    if not isinstance(key, str) or not re.fullmatch(r'[A-Za-z0-9_-]{16,128}', key):
        raise ValueError('Idempotency-Key is required')
    if not billing.checkout_configuration()['periods'][period]:
        raise billing.BillingNotConfigured('Stripe Checkout is not configured. No payment was taken.')
    _ensure_storage(subject)
    price_id = os.environ['PRICE_RESEARCHER_ANNUAL' if period == 'annual' else 'PRICE_RESEARCHER_MONTHLY']
    billing.validate_price(price_id, period)
    customer = customer_for(subject, create=True)
    rows = subscriptions(customer)
    if paid_subscription(subject, customer, rows):
        return portal(subject)
    form = {'mode': 'subscription', 'customer': customer, 'line_items[0][price]': price_id,
        'line_items[0][quantity]': 1, 'client_reference_id': subject,
        'metadata[clerk_subject]': subject, 'metadata[application]': PRODUCT,
        'subscription_data[metadata][clerk_subject]': subject,
        'subscription_data[metadata][application]': PRODUCT,
        'success_url': _base() + '/settings?billing=success',
        'cancel_url': _base() + '/pricing'}
    coupon = os.environ.get('STRIPE_FIRST_PERIOD_COUPON', '')
    if coupon and not rows:
        data = billing._req('GET', '/coupons/' + coupon)
        if not data.get('valid') or data.get('percent_off') != 50 or data.get('duration') != 'once':
            raise billing.BillingNotConfigured('The advertised first-period discount is not configured correctly.')
        form['discounts[0][coupon]'] = coupon
    result = billing._req('POST', '/checkout/sessions', form,
        idempotency='fs-checkout-' + hashlib.sha256((subject + ':' + key).encode()).hexdigest())
    if not result.get('url', '').startswith('https://checkout.stripe.com/'):
        raise billing.BillingNotConfigured('Stripe did not return a hosted Checkout URL.')
    return {'url': result['url'], 'session_id': result['id']}


def portal(subject):
    customer = customer_for(subject)
    if not customer:
        raise ValueError('no billing account exists yet')
    result = billing._req('POST', '/billing_portal/sessions', {'customer': customer, 'return_url': _base() + '/settings'})
    if not result.get('url', '').startswith('https://billing.stripe.com/'):
        raise billing.BillingNotConfigured('Stripe did not return a hosted billing portal URL.')
    return {'url': result['url']}


def webhook(event):
    """No cached grant from unordered events. Validate binding and re-read Stripe.

    Duplicate delivery is harmless: no credits, emails or grants are issued.
    A temporary provider failure returns 503 so Stripe can retry the delivery.
    """
    if bool(event.get('livemode')) != os.environ.get('STRIPE_SECRET_KEY', '').startswith(('sk_live_', 'rk_live_')):
        raise ValueError('wrong Stripe event mode')
    obj = (event.get('data') or {}).get('object') or {}
    meta = obj.get('metadata') or {}
    if meta.get('application') != PRODUCT:
        return {'received': True, 'ignored': True}
    subject = meta.get('clerk_subject', '')
    customer = customer_for(subject)
    if not customer or customer != obj.get('customer'):
        raise ValueError('webhook customer binding mismatch')
    plan(subject)  # Authoritative read; never trust event order or redirect state.
    return {'received': True}
