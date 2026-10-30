# Test coverage and verification — 0.38.0

The release passed **246 Python tests** with the real local Firestore emulator,
and **28 Node tests**. Twelve legacy SQLite test-fixture ResourceWarnings remain;
they did not fail the suite. Provider calls use fixtures; those are not live model
or physical-hardware validation. Actual live Stripe catalog/price/coupon/webhook
configuration was verified separately without creating a payment.

| Scope | Line coverage | Branch coverage | Artifacts |
|---|---:|---:|---|
| Python engine, agents, integrations, API services | 89.44% | 76.98% | coverage/full.xml and full.lcov |
| Nine new path/media/identity/workbench modules | 97.98% | 90.93% | coverage/workbench-new.xml and workbench-new.lcov |
| Scene editing and Stripe contract modules | 100.0% | 96.67% | coverage/workbench-release.xml |
| Pure browser geometry, sizing and request-state helpers | 99.19% | 95.56% | coverage/web-scenes.lcov |

The browser number does not measure the whole DOM application. The Python number
excludes CLI operator scripts, the small standalone SDK and browser code; SDK HTTP
flows and catalog setup fixtures are also executed by tests but are not included
in that percentage. No missing code or excluded GPU execution is reported as covered.
Raw XML sources are normalized to the repository root; executed hit counts and
percentages are unchanged. Source hashes are in docs/WORKBENCH_VALIDATION.json.

## Reproduce

```sh
pip install -e '.[dev]'
# Includes an isolated, checksum-verified Firestore emulator and mandatory gates:
bash scripts/verify-firestore-emulator.sh
# Or, against your already-running local emulator:
FIRESTORE_EMULATOR_HOST=127.0.0.1:56654 python -m pytest -q \
  --cov=engine --cov=agents --cov=integrations --cov=services --cov-branch \
  --cov-report=xml:coverage/full.xml --cov-report=lcov:coverage/full.lcov
node --test tests/*.test.mjs
```

CI fails on test failure, absent/invalid reports, new-module line coverage below
90%, or new-module branch coverage below70%. It retains the existing stricter
scene/billing and browser-helper gates and uploads the machine-readable reports.

## Evidence and limits

Tests cover scene/object/media ownership, exact nested-waypoint JSON round trips,
version conflicts, bounded concurrent saves, audit/idempotency behavior, scoped key
revocation, provider-key encryption/context isolation, one-shot model receipts,
path rejection/stale edits, real decodable PNG/GIF exports, and REST/MCP/SDK parity.
A* does not reserve moving actors; prediction is constant-velocity extrapolation;
simulation is not a physical safety certification. Same-process transaction
contention is bounded; Firestore transactions remain the cross-instance authority.
Emulator tests do not establish production IAM/index readiness or load capacity.

Checkout remains gated until production Clerk DNS and a restricted Firestore
credential are verified. The current development login is preserved. See
CLERK_SETUP.md and BILLING_DEPLOYMENT.md. No customer was charged or emailed.
