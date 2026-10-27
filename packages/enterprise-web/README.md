# Quantura enterprise web

Server-only Clerk verification and Firestore persistence shared by Quantura product websites. The browser never receives Firestore credentials. No cloud resources are created by this package.

## Integration

Import `workspaceServer` from `@quantura/enterprise-web/server`. Supply a fixed product slug, name, workflow stages and trusted canonical origins. Mount its `api`, `mcp` and `support` methods in Node.js route handlers. Import `WorkspacePanel` and `OrganizationSettings` from `/client` in the UI. Production dependencies must use an immutable release archive and lockfile integrity.

Required server environment: `CLERK_SECRET_KEY`, `CLERK_ISSUER`, `CLERK_AUTHORIZED_PARTIES`, `FIRESTORE_PROJECT_ID`, `WORKSPACE_AUDIT_SECRET`. Clerk's publishable key is `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`. Optionally pin `CLERK_JWT_KEY` for networkless verification. Use an existing Native-mode database, optionally `FIRESTORE_DATABASE_ID` (default `(default)`). Explicit ADC/workload identity requires `FIRESTORE_USE_ADC=true`; alternative credentials are a server-secret `FIRESTORE_SERVICE_ACCOUNT_JSON` whose project must match. Never prefix secrets with `NEXT_PUBLIC_`.

Clerk Organizations must be enabled with optional membership. The included organization configuration supports 20 members; no paid B2B add-on is purchased. Personal and organization plans/features are checked independently using `user:` and `org:` prefixes. Configure Starter/Pro/Enterprise plans and features (`api_access`, `export`, `audit_logs`, `analytics`) in the relevant Clerk instance before selling them. A shared Clerk instance intentionally shares entitlements across products; use distinct instances or explicit product features if products must be sold independently.

## Data and concurrency

Records live at `quantura_web/{product}/tenants/{user_USER_ID|org_ORG_ID}/records/{uuid}`. Product identity is fixed in server code; tenant/role/plan come only from the verified session. A caller cannot select another tenant in a request. `X-Workspace-Organization` is an optional constraint that rejects a stale organization session, never an authority to change scope.

Mutations transact the record, workspace counters, idempotency receipt and signed audit event together. Versions prevent lost updates. Idempotency keys are bound to actor, operation and body for seven days; reuse the same key after uncertain responses. IDs are generated outside retry callbacks. No LLM calls or other external side effects occur inside transactions. Only personal owners or organization administrators can delete records.

Lists use field projections and bounded cursor pagination (100 summaries maximum). Exports require `export` and contain at most 20 full records per page. Follow `next`; a page is not a complete export. Payloads are limited to 256 KiB, 10,000 nodes and eight nested levels. Free/Starter/Pro/Enterprise allowances are respectively 25/500/5,000/20,000 stored records and 100/2,000/20,000/100,000 mutations per UTC calendar month. Allowances are shared by an organization, not per seat. The website does not promise unlimited compute.

A durable minute counter caps requests at 60 free or 300 paid per tenant; MCP transport and tool calls both count. Support has a separate five-per-minute budget. Counters add one transaction per request. The single-tenant counter/chain can contend under sustained concurrent writes; production load tests and a sharded/ordered design are required before increasing limits.

## Security and lifecycle

The Google server SDK bypasses Firestore Security Rules. Server authorization is mandatory. Direct browser/client access must be denied. Review the **published** production rules before enabling: a broad pre-existing allow can override a new narrow deny. Use the supplied rules fragment as a merge aid, never overwrite an unrelated project's rules. An existing project may already serve other Quantura products.

IAM credentials can access their authorized database beyond these application namespaces. Code isolation is not an IAM security boundary against a compromised server. Prefer short-lived workload identity and separate databases/projects for stronger product isolation. No IAM roles or keys are created by this package.

Idempotency receipts expire after seven days and request counters after two days. Configure TTL on `expiresAt` only after reviewing billable cleanup and retention. TTL is asynchronous; application correctness does not depend on deletion timing. Records and content-free audits have no automatic retention deletion yet. Deleting a record removes its payload, not historical actor IDs/hashes. Account erasure and an approved audit-retention policy require an operator workflow; no automatic Clerk deletion webhook is claimed. Exempt large payload/result maps from indexing using the supplied candidate index configuration.

Audit verification checks HMACs, hashes, tenant binding and links in a consistent latest window. It does not detect a privileged rollback of the database or deletion of an entire namespace. HMAC key rotation requires an explicit migration/key-version design; changing the secret makes older verification fail. Use secret managers; never store descriptors, credentials, raw request bodies or customer payloads in logs.

## HTTP and MCP

The generated OpenAPI 3.1 specification describes only implemented workspace endpoints. API/MCP require `api_access`; the UI's basic saved-record surface is available to free signed-in users. Authentication uses short-lived Clerk session Bearer tokens. API keys, refresh-token flows and automatic MCP OAuth discovery are **not** configured. Do not advertise a ChatGPT OAuth connection until an authorization server/client flow has been configured and tested.

MCP uses official SDK v2 through `mcp-handler` 2.3.0, with stateless HTTP POST and no subscription/session storage. Each request constructs callbacks with its own verified identity. Tools save/read records and update status only; they never execute the private repositories' cloud, tool, trading, model or physical actions. User record contents remain untrusted data.

Support answers from bounded product documentation by default. Optional NVIDIA inference requires `SUPPORT_AI_FREE_ENDPOINT_VERIFIED=true`, `NVIDIA_API_KEY`, and a verified model ID. Only the explicit question and documentation facts are sent; customer records and identity are not attached or logged. Provider failure or quota falls back to documentation, never a paid provider. The UI labels answer mode. No inference was run during local tests; the provider test uses a deterministic HTTP fixture.

## Billing

50% applies to **one** billing period (first month or first annual invoice), then full renewal. Integer-cent quote math is tested; it is not a coupon. Advertise only after an actual Clerk/Stripe production promotion is created and independently verified, then enable `LAUNCH_PROMOTION_ENABLED`, `LAUNCH_PROMOTION_VERIFIED`, `LAUNCH_PROMOTION_CODE`. `BILLING_PROVIDER_VERIFIED=true` enables the hosted pricing table. Test-instance plans do not prove production payment readiness. No live prices, coupons or subscriptions were changed by the code integration.

## Validation

Node 24+ and Java 21 are required. Install with `npm ci`. Run the Firestore emulator with a `demo-` project and deny-all client rules, then:

```sh
FIRESTORE_EMULATOR_HOST=127.0.0.1:8080 npm run coverage
npm run build
```

The package tests actual Clerk RSA signature verification, real Firestore emulator transactions, cross-product/tenant denial, concurrent updates, idempotency, quotas, audit tampering and real MCP client/server negotiation. The emulator tests are skipped without the emulator; CI must fail on unexpected skips. Coverage covers server `.ts` modules; React `.tsx` UI is a separate browser-validation surface, not included in the server percentage. No real cloud write, production index/load test, payment or provider-LLM execution is implied.

References: [Clerk sessions](https://clerk.com/docs/guides/sessions/session-tokens), [Firestore server SDK](https://docs.cloud.google.com/firestore/native/docs/create-database-server-client-library), [transactions](https://docs.cloud.google.com/firestore/native/docs/manage-data/transactions), [server rules bypass](https://firebase.google.com/docs/firestore/security/rules-conditions), [index best practices](https://firebase.google.com/docs/firestore/best-practices), [MCP handler](https://github.com/vercel/mcp-adapter).
