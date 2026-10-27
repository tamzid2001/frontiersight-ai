# Auth & billing — what is real today, and the production path

## Today (hackathon build, honest labels)
- **Profiles are device-local.** "Sign in" creates a profile (name + email)
  stored in `localStorage`; scenes, runs and onboarding are scoped per profile
  (`fs-my-scenes:<id>`, `fs-runs:<id>`). No password is collected, nothing is
  sent to a server, and clearing browser data deletes the profile. The UI says
  exactly this next to the form. It is a profile switcher for demos and
  single-device use — **not** an identity system and not a security boundary.
- **Billing does not exist.** The Pricing page shows planned launch prices,
  marks planned features with ◷, and the waitlist stores entries locally in
  this build. No payment provider is connected and no charge can occur.

## Production path (drop-in, not yet enabled)
1. **Identity:** Clerk or any OIDC provider in front of the same views; the
   server verifies the session JWT on every `/api/*` call and replaces the
   `guest/profile` storage scoping with the verified `user_id`/`org_id`.
   Env: `CLERK_PUBLISHABLE_KEY`, `CLERK_SECRET_KEY` (server-side only).
2. **Persistence:** Postgres for users/orgs/runs, object storage for media;
   the stateless analysis API already takes full track payloads, so no
   engine changes are needed.
3. **Billing:** Stripe Checkout + Customer Portal wired to the Pricing page
   buttons; plans enforced server-side (rate limits, SAM video mode, saved
   scene quotas) rather than by hiding UI. Env: `STRIPE_SECRET_KEY`,
   `STRIPE_WEBHOOK_SECRET`. Webhook verifies subscription state before any
   paid feature unlocks.
4. **Meta costs:** production deployments use the customer's own
   `MODEL_API_KEY`; Meta Model API usage is billed by Meta and is never
   marked up or resold by FrontierSight plans.

## Execution prompt

The complete, ready-to-run integration spec for turning the Researcher ($19/mo)
and Team/Enterprise (custom) plans into a live, server-enforced billing system
(Stripe + Clerk + Postgres, entitlements matrix, webhook lifecycle, Team quote
flow, tests and rollout) lives in `docs/PAID_PLANS_INTEGRATION_PROMPT.md`.
It ends with the owner checklist of keys/decisions required to start.
