# Authentication and billing

The current implementation uses verified Clerk identities and a stable Clerk
subject to bind Stripe customers. Private workspace libraries use Firestore when
configured; per-instance legacy SQLite is not a durable subscription authority.
No PostgreSQL adapter or production deployment is claimed merely by setting a
DATABASE_URL. Production payments are gated on live Clerk and Stripe credentials
and a verified durable storage write.

See [BILLING_DEPLOYMENT.md](BILLING_DEPLOYMENT.md),
[CLERK_SETUP.md](CLERK_SETUP.md) and [WORKBENCH_API.md](WORKBENCH_API.md) for the
current architecture, API/agent authentication, operations and activation status.
Historical plans remain in Git history; they are not the active implementation.
