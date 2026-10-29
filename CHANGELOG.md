# Changelog

## 2026-10-29 — bounded scene candidates and human proportions

- Choose 1–8 parallel candidates, display one scene, and stop without automatic retries.
- Add cancellation, shared deadlines, bounded response reads and process backpressure.
- Preserve edits against late generation results and render model text safely.
- Cap illustrative human heights independently of collision clearance in all 3D viewers.
- Publish the generation API contract and regression tests.

Validation: 176 Python tests passed, 6 optional integration tests skipped;
26 Node tests passed. Web helper coverage: 99.09% lines, 95.65% branches.

## 0.38.0 — Authenticated workbench and automatic paths

- Added bounded A* static-obstacle planning, timestamped constant-velocity
  prediction, and validated one-shot Muse path edits. Stable object IDs, custom
  recipes and floor dimensions survive every editor/view handoff.
- Added shared authenticated REST/MCP scene, object and media libraries, object
  reuse, rendering, version checks, durable idempotency and model receipts.
- Added scoped, expiring/revocable personal agent keys, a Python client, and
  authenticated remote stdio bridge. Anonymous offline analysis remains supported.
- Added real PNG frame and animated GIF preview exports using playback dynamics;
  these are explicitly simulated 2D output, not camera measurements or MP4.
- Implemented stable Clerk-subject Stripe Checkout/portal binding and authoritative
  subscription checks, raw-body webhook validation/rotation, optional first-period
  promotion, explicit catalog setup and usable /pricing and /settings routes.
  Production activation requires deployment credentials; no live payment tested.
- Fixed Firestore nested-waypoint persistence by encoding bounded canonical JSON.
  Added emulator integration, contract, billing and negative-path tests, coverage
  artifacts/gates, OpenAPI, served API guide and operational documentation.
