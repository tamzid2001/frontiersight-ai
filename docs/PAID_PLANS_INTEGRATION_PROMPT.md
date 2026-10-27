# Execution prompt — fully integrate Researcher ($19/mo) and Team/Enterprise (Custom) plans

> Paste this entire prompt to the implementing engineer/agent. It assumes the
> FrontierSight AI repo (`tamzid2001/frontiersight-ai`) at v0.12.x, deployed on
> Vercel (`frontiersight-ai.vercel.app`), Python-stdlib API + vanilla JS frontend.

---

## ROLE

You are a senior full-stack engineer specialising in SaaS billing. You will turn
FrontierSight AI's honestly-labelled planned pricing into a real, payable,
server-enforced subscription system — without breaking the free Explorer tier,
the deterministic engine, or the product's honesty rules. You do not invent
credentials: where a secret or business decision is missing, you build
everything up to that seam, keep the feature safely disabled, and report the
exact blocker.

## CONTEXT (verified current state — read these first)

- Pricing page (`apps/web/index.html`, `view-pricing`) currently shows:
  Explorer $0 (available now), Researcher **$19/mo** (annual $190 planned),
  Team/Enterprise **Custom**, with ✓ = available / ◷ = planned marks and the
  statement "Billing is not enabled in this hackathon build". Waitlist buttons
  store entries in `localStorage` only. Test
  `tests/test_regressions.py::test_pricing_and_auth_are_honest` pins the words
  "Billing is not enabled" and forbids "stripe"/"checkout" strings — you will
  update that test only when billing is genuinely live in test mode.
- Auth today is device-local profiles (`localStorage`, no server account) and is
  labelled as demo authentication. `docs/AUTH_AND_BILLING.md` describes the
  intended production path (Clerk/OIDC + Postgres). Paid plans require real
  accounts: **auth is a prerequisite, not an optional extra**.
- API: zero-dependency Python (`services/api/server.py`), stateless; Meta calls
  spend the host's `MODEL_API_KEY`; per-client quotas: 120 POST/min general,
  30 POST/min on `/api/meta/*`.
- Product honesty rules (non-negotiable): deterministic verdicts never depend
  on payment; offline/fixture mode never fakes live model output; exported
  evidence keeps its labels; no safety-certification claims.

## OWNER INPUTS REQUIRED BEFORE LIVE CHARGES (build to these seams; use Stripe
TEST mode until provided)

1. `STRIPE_SECRET_KEY` (test, then live), `STRIPE_WEBHOOK_SECRET`,
   `STRIPE_PUBLISHABLE_KEY`.
2. Stripe Product/Price IDs, or authority to create via API:
   `PRICE_RESEARCHER_MONTHLY` ($19/mo), `PRICE_RESEARCHER_ANNUAL` ($190/yr).
3. Auth provider keys: Clerk (`CLERK_PUBLISHABLE_KEY`, `CLERK_SECRET_KEY`) or an
   explicit decision to ship a first-party email-link auth instead.
4. A persistence choice: Vercel Postgres/Neon connection string (`DATABASE_URL`)
   for users, subscriptions, entitlements, waitlist migration, audit log.
5. Business decisions: 14-day Researcher trial or none (default: **none** —
   card up front, cancel anytime); refund policy text; support email;
   Team/Enterprise sales contact + whether quotes are manual (default: manual).
6. Tax posture: Stripe Tax on or off (default: off in test, owner confirms
   before live).

## GOAL

A visitor can: sign up (real account) → subscribe to Researcher via Stripe
Checkout → immediately gain Researcher entitlements enforced **server-side** →
manage/cancel in the Stripe Customer Portal → lose entitlements on
cancellation/past-due per the lifecycle below. A team buyer can request a
custom quote and be provisioned manually with org-scoped entitlements,
including SSO/SAML via Clerk Organizations. The free Explorer tier keeps
working exactly as today for anonymous/local users.

## ENTITLEMENTS MATRIX (enforce server-side; UI badges are cosmetic)

| Capability | Explorer (free) | Researcher $19 | Team/Enterprise (custom) |
|---|---|---|---|
| Built-in scenarios, Create Lab, deterministic analysis | ✓ | ✓ | ✓ |
| Host-key Meta calls (fair use) | 30/min/IP (current) | — (own key) | — (own key) |
| Bring your own `MODEL_API_KEY` (stored encrypted, used per-user) | ✗ | ✓ | ✓ |
| SAM 3.1 video-mode tracking (`/api/meta/segment` with video) | ✗ | ✓ | ✓ |
| Saved scenes / runs | 10 scenes / 20 runs (local) | Unlimited (server-persisted) | Unlimited + shared org library |
| Counterfactual Monte-Carlo runs per analysis | 200 (current default) | 2,000 | Custom |
| Evidence export with recorded approval | ✓ | ✓ | ✓ + org audit-log retention (≥ 12 mo) |
| Support | Community | Priority (email) | SLA (contracted) + onboarding |

## ARCHITECTURE

- **Identity:** Clerk (hosted UI components dropped into the existing auth
  view; keep device-local profiles as "guest mode"). Server verifies Clerk
  session JWT on every entitled endpoint (`Authorization: Bearer`), maps
  `user_id`/`org_id` to entitlements. Never trust plan claims from the client.
- **Billing:** Stripe Billing. Checkout Sessions (mode=subscription) created
  server-side; success/cancel URLs back into the app (`/settings?billing=…`).
  Customer Portal sessions for manage/cancel/update-payment. Webhook endpoint
  `/api/billing/webhook` verifies `Stripe-Signature` with the raw body,
  is idempotent on event id, and is the **only** writer of subscription state.
- **Persistence:** Postgres tables `users(id, clerk_id, email, created_at)`,
  `subscriptions(id, user_id, org_id, stripe_customer_id, stripe_sub_id,
  price_id, status, current_period_end, cancel_at_period_end)`,
  `entitlements(user_id/org_id, key, value, source, updated_at)` (derived cache
  rebuilt from subscription state), `waitlist(email, plan, created_at, converted)`,
  `audit_log(id, org_id, actor, action, artifact_id, ts)` for Team.
- **BYOK:** per-user Meta key encrypted at rest (libsodium/KMS; never logged,
  never returned after save — show last-4 only). When present, `/api/meta/*`
  uses the caller's key and skips host-quota accounting; otherwise host key +
  existing quotas apply.
- **Enforcement points (server, all returning 402 with `{error, upgrade_url}`
  when unentitled):** SAM video payloads, MC runs > 200, server-persisted
  scenes beyond quota, org sharing endpoints. Free/anonymous path is untouched.
- **Team/Enterprise:** no self-serve checkout. "Contact sales" → quote-request
  form (company, seats, deployment needs) stored + emailed to the owner;
  provisioning is a documented admin script (`scripts/provision_org.py`) that
  creates the Clerk Organization, assigns the custom entitlement set and price
  override in Stripe (manual subscription), and writes the audit-log seed.
  SSO/SAML is Clerk Organizations' enterprise connection — configure, don't
  build. Private deployment (VPC) and SLA are contractual: the app work is
  org entitlements + audit-log retention + a deployment runbook
  (`docs/ENTERPRISE_DEPLOYMENT.md`), not code for the VPC itself.

## FLOWS TO IMPLEMENT

1. **Upgrade:** Pricing "Subscribe" (Researcher) → signed-in? no → Clerk sign-up
   → `POST /api/billing/checkout` → Stripe → return → webhook
   `checkout.session.completed` + `customer.subscription.created/updated` →
   entitlements active → UI shows "Researcher · active" (from `/api/me`).
2. **Manage:** Settings → "Manage billing" → Portal session → cancel at period
   end → entitlements persist until `current_period_end`, then Explorer.
3. **Failure lifecycle:** `invoice.payment_failed` → status `past_due`,
   7-day grace with in-app banner → `subscription.deleted` → Explorer.
   Webhook handler must tolerate out-of-order events (use `created` + stored
   status machine: trialing→active→past_due→canceled).
4. **Waitlist conversion:** existing local waitlist entries prompt a one-click
   import on sign-up (email match → mark converted; never silently upload
   browser data without the user pressing import).
5. **Downgrade safety:** losing Researcher never deletes user data; BYOK key is
   deleted on downgrade (with notice), server scenes become read-only above
   quota until under it again.

## FRONTEND CHANGES

- Pricing page: replace "waitlist open" Researcher CTA with **Subscribe**
  (signed-in) / **Create account to subscribe** (anonymous); annual toggle
  drives the real Price IDs; remove "Billing is not enabled" only for the
  surfaces that are live, and update the pinning test accordingly. Team CTA →
  quote-request modal/page (company, work email, seats, needs) posting to
  `/api/sales/quote`.
- Settings: plan card (current plan, status, period end, cancel state),
  "Manage billing" (Portal), BYOK key form (write-only, last-4 display),
  usage this period (Meta calls, MC runs) from server counters.
- Header: plan badge next to profile ("Explorer"/"Researcher"/org name).
- Paywall moments: hitting a gated action shows an upgrade modal naming the
  exact limit hit and the plan that removes it — never a dead end.

## BACKEND/API SURFACE

`GET /api/me` (identity + entitlements + usage) · `POST /api/billing/checkout` ·
`POST /api/billing/portal` · `POST /api/billing/webhook` (raw body, signature
verified) · `PUT/DELETE /api/keys/meta` · `POST /api/sales/quote` ·
`GET /api/admin/audit` (org admin only, Team). All entitled routes share one
`require_entitlement(key)` guard. Structured logs include `request_id`,
`user_id`, `stripe_event_id` — never keys or card data (Stripe handles PCI;
we never touch card numbers).

## SECURITY & COMPLIANCE

Secrets only in env; webhook signature verification before any parsing;
idempotency keys on Checkout creation; CSRF not applicable (Bearer auth, no
cookies) or SameSite cookies if Clerk session cookies are used; BYOK encrypted
with a key from env/KMS, rotation documented; audit-log Team actions
(provisioning, exports, approvals) with actor + timestamp; GDPR: account
deletion endpoint erases user rows, BYOK secret, and stored scenes, and
cancels any live subscription first.

## TESTS (all must exist and pass)

- Unit: entitlement resolver matrix; webhook state machine incl. out-of-order
  and duplicate events (same event twice → applied once); BYOK encryption
  round-trip; quota gates return 402 with `upgrade_url`.
- Integration (Stripe test mode / recorded fixtures): checkout→webhook→
  `/api/me` shows Researcher; cancel→period-end→Explorer; payment_failed→
  grace→deleted. Webhook with a bad signature → 400 and no state change.
- Browser (Playwright, test mode): anonymous → pricing → sign-up → subscribe
  with card `4242…` → badge flips to Researcher → gated SAM-video action
  succeeds → Portal cancel → banner shows cancel date. Team quote form
  submits and stores. Existing 39-check flow audit + 49 unit tests stay green;
  `test_pricing_and_auth_are_honest` is rewritten to assert the now-true
  claims (prices, enforcement, test-mode labelling until live keys land).
- No test may call live Stripe or charge a real card.

## ROLLOUT

1. Test mode end-to-end on a preview deployment; owner walkthrough with
   `4242…`. 2. Webhook endpoint registered in Stripe (test), events:
   `checkout.session.completed`, `customer.subscription.*`,
   `invoice.payment_failed`. 3. Waitlist email announcing Researcher with
   import link. 4. Live keys swapped by owner only; "Billing is not enabled"
   copy removed the same deploy; pricing page labels switch from Planned to
   live; monitor webhook failures for 48h. 5. Team: publish quote form +
   runbook; first org provisioned manually with the owner on call.

## DEFINITION OF DONE

Subscribe→entitled→gated-action→portal-cancel→downgrade works in Stripe test
mode against the deployed preview; every entitlement in the matrix is enforced
by a server test; webhook forgery is rejected; no secret or card data in logs
or repo; CI + browser audits green; README/Pricing/`docs/AUTH_AND_BILLING.md`
updated to describe the now-true state; and a short `docs/BILLING_RUNBOOK.md`
covers webhook replay, refund issuance (Stripe Dashboard), BYOK rotation, and
org provisioning. If any owner input is missing, ship everything up to that
seam with the feature disabled and the blocker stated — do not mock a payment
flow and present it as integrated.

---

### Owner checklist (reply with these to start execution)

- [ ] Stripe test keys + webhook secret (or "create products via API in test mode")
- [ ] Clerk keys, or "build first-party email-link auth instead"
- [ ] `DATABASE_URL` (Vercel Postgres/Neon) provisioned
- [ ] Trial: none (default) / 14 days
- [ ] Support + sales email addresses; Stripe Tax on/off
