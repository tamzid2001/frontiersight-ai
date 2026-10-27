# Clerk setup — what is configured, and how to finish it

Status at 0.27.0: a dedicated Clerk application **FrontierSight AI**
(`app_3LIU7UyTiPCKA7yPOo4t90kvukP`) exists, the project is linked, and
Billing is enabled on the **development** instance with this catalog:

| Plan (slug) | Payer | Price in Clerk | Features |
|---|---|---|---|
| Free (`free_user`) | user | $0 (Clerk default) | — |
| Researcher (`researcher`) | user | **$19/mo**, annual-monthly $15.83 (≈$190/yr) | `byok`, `sam_video`, `unlimited_scenes`, `mc_2000`, `priority_support` |
| Team (`team`, hidden) | org | Custom — not publicly visible | all Researcher features + `org_workspace`, `audit_log` |

## How the integration works (already coded)

- **Frontend** (`apps/web/app.js:initClerk`): fetches `/api/auth/config`;
  only if `CLERK_PUBLISHABLE_KEY` is set does it load ClerkJS v5, mount
  `<SignIn>` in the auth view, mount `<UserButton>` in the header, and mount
  the Clerk `<PricingTable>` on Pricing (custom cards hide when it renders).
  If Clerk fails or is unconfigured, email/password accounts keep working
  and the UI says exactly that.
- **Identity sync**: after Clerk sign-in the browser sends the Clerk session
  JWT to `POST /api/auth/clerk-sync`; the server verifies it against the
  instance JWKS (RS256, issuer check — `integrations/clerk_auth.py`), then
  provisions/links the local user and issues the normal FrontierSight
  session. All entitlements, scenes, BYOK and gates work unchanged.
- **Billing sync**: Clerk webhooks → `POST /api/webhooks/clerk` (Svix
  signature verified; Clerk event names, e.g. `subscriptionItem.canceled`,
  not Stripe's). Subscription state flips the same `plan_for()` used by the
  Stripe path: `clerk:researcher` → Researcher; anything else → Explorer.
- **Go-live checklist** (owner): create the webhook endpoint in Clerk
  Dashboard → Developers → Webhooks pointing at
  `https://frontiersight-ai.vercel.app/api/webhooks/clerk`, subscribe to
  `user.created/updated/deleted`, `subscription.*`, `subscriptionItem.*`,
  `paymentAttempt.*`, then set `CLERK_WEBHOOK_SIGNING_SECRET` in Vercel.
  For production, claim/create the production instance, rotate to
  `pk_live_/sk_live_` keys, and connect a Stripe account in Clerk Billing
  settings (development instances use Clerk's shared dev gateway).

## Environment variables

| Var | Where | Notes |
|---|---|---|
| `CLERK_PUBLISHABLE_KEY` | Vercel + browser | Public by design. Currently the dev instance key. |
| `CLERK_SECRET_KEY` | Vercel (server) | Only needed for Backend API calls; JWT verification does not use it. |
| `CLERK_WEBHOOK_SIGNING_SECRET` | Vercel (server) | From the webhook endpoint; webhooks return 503 until set. |

Locally: `clerk env pull` refreshes `.env.local` (gitignored).
CLI: `clerk doctor --json` · `clerk config pull --keys billing` ·
`clerk enable billing` (already done for this app).
