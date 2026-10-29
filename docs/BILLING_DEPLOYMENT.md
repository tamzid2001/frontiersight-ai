# Stripe + Clerk billing deployment

Researcher is USD $19/month or $190/year. Where the one-time coupon is configured,
new customers receive 50% off the first billing period only ($9.50 first month or
$95 first year); renewals are $19/month or $190/year. Existing subscribers retain
their agreements. No customer email or renewal-price migration is performed.

The pricing page is `/pricing`. It uses server-declared availability. It either
opens a server-created Stripe-hosted Checkout session after Clerk sign-in, or
clearly says unavailable; it never silently substitutes a quote form. `/settings`
opens the customer's Stripe billing portal. No card data touches this application.

Set these Vercel production variables securely:

- Existing Clerk secret/public keys, issuer and authorized parties for this origin.
- `BILLING_IDENTITY=clerk`, `SCENE_STORE=firestore`.
- `FIRESTORE_PROJECT_ID`, optional database ID, restricted `FIRESTORE_SERVICE_ACCOUNT_JSON`.
- Random `WORKSPACE_AUDIT_SECRET` of at least 32 characters.
- `STRIPE_SECRET_KEY` (live in production), `STRIPE_WEBHOOK_SECRET`.
- `PRICE_RESEARCHER_MONTHLY`, `PRICE_RESEARCHER_ANNUAL`.
- Optional `STRIPE_FIRST_PERIOD_COUPON` (exactly 50%, duration=once).
- `APP_BASE_URL=https://frontiersight-ai.vercel.app`.

The deployment must have usable credentials, not masked export strings. Vercel
sensitive variables cannot be recovered from `vercel env pull`. Never commit
credentials, webhook secrets or `.env` outputs.

With a Stripe key in your environment, `python scripts/configure_stripe.py --apply
--out /private/path/frontier-stripe.env` creates/reuses only this product's prices,
coupon and webhook. It does not charge anyone or change existing subscriptions.
Review the generated private file and place its values in Vercel. The script
requires explicit --apply and writes secrets with mode0600; output is not a commit
artifact. Configure the customer portal in Stripe if not already enabled.

Customer pointers are in Clerk **private** metadata keyed by the stable Clerk
subject, independent of ephemeral SQLite numeric IDs. Customer metadata must bind
the same subject and application. Active/trialing subscriptions with an exact
allowed product price/quantity are read from Stripe to grant paid access. The
success redirect is never proof of payment. Personal plans cannot upgrade an
unrelated organization; organization contracts are separately scoped.

Webhooks verify the raw-body HMAC, timestamp and any valid rotated v1 signature.
They re-fetch authoritative state instead of granting from stale unordered events.
Repeated deliveries cannot grant duplicate credits. A provider outage fails closed
with 503. Add payloadJson and resultJson Firestore index exemptions for stored JSON
fields; they are not queried. JSON serialization preserves nested waypoint arrays
that native Firestore arrays cannot represent. No new IAM or cloud resource is
created automatically.

Before launch: verify test-mode Checkout, portal, cancellation, expiry, webhook
replay/signature failures, account isolation, and Firestore writes. Then switch
both prices and keys to live and verify the actual hosted Checkout without paying.
A live payment and customer email are not required for deployment verification.
