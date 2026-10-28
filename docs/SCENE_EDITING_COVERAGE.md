# Workbench release verification — 2026-10-28

Baseline: `56379df` on `main`. Measurements are local execution evidence, not
claims of physical robot validation, measured image depth or full UI coverage.

| Scope | Tests / executed evidence | Line coverage | Branch coverage | Artifact |
|---|---|---:|---:|---|
| Complete Python suite | 166 passed, zero skipped; actual local Firestore emulator | — | — | Raw command/log recorded in release workspace |
| `engine.scene_edit` | Full-suite execution: resize, movement, canonical handoff, simulation, HTTP/MCP/stdio | 100% | 100% | `coverage/workbench-release.xml` |
| `integrations.billing` | Price validation, readiness, signed webhooks and real HTTP to a local provider fixture | 100% | 72.22% | `coverage/workbench-release.xml` |
| Pure image/scenery/stage controls | 17 Node 24 tests | 99.44% | 96.13% | `coverage/web-scenes.lcov` |

Python emitted 11 warnings, including legacy SQLite test-connection cleanup
warnings. There were no failed or skipped tests in that run. Coverage includes
executed first-party code; it does not instrument Three.js or all DOM handlers.
The local provider fixture is not Stripe production verification or a payment.

## Reproduce

Install `.[dev]` in a Python 3.10+ virtual environment. For the complete suite,
start the Firestore emulator separately and set its actual host/port:

```bash
FIRESTORE_EMULATOR_HOST=127.0.0.1:56654 python -m pytest -q \
  --cov=engine.scene_edit --cov=integrations.billing --cov-branch \
  --cov-report=xml:coverage/workbench-release.xml --cov-report=term-missing

node --test --experimental-test-coverage \
  --test-coverage-lines=90 --test-coverage-branches=70 --test-coverage-functions=90 \
  --test-reporter=spec --test-reporter=lcov \
  --test-reporter-destination=stdout --test-reporter-destination=coverage/web-scenes.lcov \
  --test-coverage-include='apps/web/*core.mjs' --test-coverage-include='apps/web/*core.js' \
  tests/web-scenes.test.mjs
```

CI retains the complete Python suite, overall Cobertura/LCOV artifacts and the
Node gate. An additional scene/billing contract step validates nonempty XML,
requires at least 90% line and 70% branch coverage for each of the two modules,
and uploads that raw report. CI without an emulator explicitly skips the
emulator-dependent tests; the local full-suite result above did run them.

## Actual browser checks

- 2D object drag, 3D mesh drag with orbit paused, numeric positioning, arrow-key
  movement, waypoint selection/insertion and resize fitting.
- A floor edited from 8 × 7 to 9 × 8 m appeared with the same two components in
  Studio and Counterfactual. Both WebGL viewers rendered without console errors.
- Counterfactual playback used its 6.2-second sampled duration rather than a
  hard-coded six seconds. The separation chart remained available when expanded.
- A 1280 × 768 initial Counterfactual workspace fit inside the viewport. At
  390 × 844 the interfaces had no horizontal overflow; content scrolls vertically.
- Studio segmentation disclosure opened its attributed gallery without inference.
- Annual Researcher CTA displayed $190/year and monthly displayed $19/month.
- The real Clerk sign-in component rendered with the new surrounding layout.
  The connected Clerk instance is still development, not production.

No GPU compute benchmark, physical safety certification, live Stripe transaction
or production Clerk activation is claimed. See `PRODUCTION_ACTIVATION.md`.
