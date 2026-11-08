# Changelog

## 2026-11-08 — guided first-run proof flow (Upload → Inspect → Intervene → Review)

- New `apps/web/wizard-core.mjs` (pure ESM state machine) gates the four-step
  guided flow: upload a fixture or workspace scene, inspect engine-sampled
  tracks, declare an intervention (labelled ASSUMPTION) and record the real
  deterministic run (manifest hash, labelled DETERMINISTIC).
- Export of the proof packet stays LOCKED until a named human approves the
  evidence — the same approval rule the Evidence view applies — and every
  packet states it is not a safety certification.
- Scene validation mirrors the engine's accepted request shapes (fixture
  scenario payload, object-based scene, raw tracks); fixture payloads keyed
  by `id` and by `scenario` are both accepted.
- The guided view is reachable from the home CTA and the `/guided` deep link;
  it deliberately takes no primary-nav slot (the grouped-nav budget guard in
  tests/test_regressions.py still holds).
- `/wizard-core.mjs` and `/guided` are wired through the Vercel rewrite layer
  (vercel.json + `_route()` in services/api/server.py) exactly like the other
  app modules; the SPA title for `/guided` is "Guided Proof".
- No model inference is claimed anywhere in the flow; FIXTURE / USER_SCENE /
  ASSUMPTION / DETERMINISTIC provenance labels are carried end to end, and
  occlusions are recorded as missing evidence, separate from uncertainty.

Validation: 311 Python tests passed, 29 optional-integration tests skipped;
32 Node tests for the new wizard core; 62 Node tests passed overall.
Web helper coverage (node --test gate): 98.77% lines, 91.47% branches,
97.65% functions — wizard-core.mjs alone: 98.40% / 84.83% / 93.33%.
Live end-to-end check on the local server: fixture upload → 2-track inspect
→ deterministic counterfactual run (manifest e317916e01f10233…, d_min
0.166 m → 2.349 m) → approved, exported packet.

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
