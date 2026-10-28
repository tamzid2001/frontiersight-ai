# Production authentication and billing: remaining gates

Observed on 2026-10-28:

- Clerk CLI resolves this repository to the FrontierSight AI application.
  It reports `not_started`, no production domain and no production instance.
- Vercel has Clerk development credentials, but no Stripe billing variables.
- The native account/subscription store is SQLite. Its Vercel `/tmp` file is
  per-instance and ephemeral. Merely setting a PostgreSQL URL does not implement
  a PostgreSQL adapter: the present store supports SQLite only.

The workbench, deterministic API and MCP can operate without paid checkout.
`GET /api/billing/config` reports availability without secret values. Unavailable
Researcher enrollment opens an explicit access request; it does not charge or
silently join a waitlist. Live checkout fails closed on this Vercel store.

## Required activation work

1. Complete the human Clerk production setup from this repository with
   `clerk deploy`. Choose an owned production domain and complete DNS, SSL,
   email DNS and OAuth configuration. Verify with `clerk deploy status`.
2. Install the resulting production credentials as encrypted Vercel variables.
   Verify sign-in, sign-up, sign-out, organization switching, server JWT
   verification and existing-account continuity. Do not rename development
   credentials to make them appear production-ready.
3. Implement and validate a durable account/subscription/session store. Include
   cross-instance consistency, migrations, transaction-safe webhook receipts,
   backup/recovery, tenant access checks and retention. Preserve the existing
   persistence API; do not enable payment against the ephemeral SQLite file.
4. Configure live Stripe secret/webhook keys and the actual recurring Price IDs:
   `PRICE_RESEARCHER_MONTHLY` ($19 USD/month) and
   `PRICE_RESEARCHER_ANNUAL` ($190 USD/year). Configure customer portal and the
   `/api/billing/webhook` destination. Keep all secrets outside Git.
5. Validate the complete subscription lifecycle in Stripe test mode first:
   checkout, renewal, cancellation, failed payment, retries, portal access and
   entitlement restoration across cold instances. Then verify live configuration
   and any explicitly approved live transaction.

The checkout adapter retrieves the selected Stripe price before creating a
session and verifies amount, currency, recurring interval and production live
mode against the displayed offer. Offline tests exercise both successful request
construction and rejection of mismatched prices. These tests do not establish
live account configuration or a completed production purchase.

References actually reviewed: [Clerk JavaScript SignIn](https://clerk.com/docs/js-frontend/reference/components/authentication/sign-in),
[Clerk routing](https://clerk.com/docs/guides/how-clerk-works/routing),
and [Stripe Prices API](https://docs.stripe.com/api/prices).
