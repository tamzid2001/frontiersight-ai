# Clerk deployment and identity configuration

Verified with Clerk CLI 4.1.0, using the existing FrontierSight AI application.
The repository is linked by its Git remote. `clerk doctor --json` verifies the
account, application and instance; no browser impersonation is required.

Both development and the prepared production instance allow personal accounts,
keep Organizations enabled, and cap membership at 20. Forced organization selection
was disabled because it blocked the individual Researcher subscription flow.
No paid Clerk add-on was purchased. Stripe owns this product's subscription
contract; a Clerk Billing pricing table is not substituted for Stripe Checkout.

Production was prepared for `frontiersight.quantura.studio`. Authoritative DNS
is Cloudflare; records written only to Vercel would not activate it. The current
application retains its working development identity until DNS is verified.
Production email-code verification is enabled. Google is disabled on production
until its own production OAuth credentials are available; development Google
sign-in remains unchanged. CLI status remains the verification authority.

```sh
clerk doctor --json
clerk deploy status --mode agent
# After the five required DNS CNAME records have been installed:
clerk deploy status --wait --mode agent
# Pull keys only to a private ignored file after production is verified:
clerk env pull --help
```

Use `clerk config patch --dry-run` before any instance mutation and explicitly
select the instance. Never use `init --fresh`, rotate credentials or relink to a
different application just to repair a deployment. Production payments require
live Clerk credentials, live Stripe prices/key and verified durable storage;
missing prerequisites keep checkout unavailable rather than losing paid work.

The production DNS handoff is saved locally as Desktop/FrontierSight Production
Setup.txt. It contains public DNS targets, not API keys. It is not a substitute
for successful domain/SSL/email verification. Cloud Firestore still requires an
existing restricted server credential in the deployment environment.
