# Deep code review #3 — 2026-10-27 (pre-0.12.0)

Two independent read-only audits (backend, frontend) plus owner-reported UI
defects. Verified findings fixed in 0.12.0; remaining items tracked below.

## Fixed (backend)
- Pixel coordinates could be relabelled as metres via a calibration object
  (TTC 20x wrong). Metric claims now derive only from track space.
- "Independent verification" was dishonest: manifest hash never recomputed,
  metric check inverted (honest pixel runs FAILed), hardcoded no-LLM check.
  Now: hash recomputed and compared, space-consistency check, model-proposed
  interventions disclosed as inputs.
- Upload provenance hardcoded "FIXTURE" even for user scenes; now derived.
- Workflow crashed on disjoint/insufficient/mixed-space scenes and returned
  the wrong run for a reused idempotency key. Guarded; cache key now binds
  key+fingerprint; sim initialisation failures fail the stage, not the run.
- Counterfactual accepted negative/NaN decel, infinite intervention, negative
  radii (silent physics corruption). Full finite/range validation; manifest
  now covers radii + MC parameters (schema v2).
- CPA returned a t_star beyond the horizon at which d_min did not occur.
- Server: NaN/Infinity JSON rejected, stricter track payload validation,
  unknown agent_id -> 400 (was silent wrong-agent), security headers +
  banner suppression, traversal-safe static serving, tighter 30/min quota
  on paid model endpoints, bounded rate-limiter memory.

## Fixed (frontend)
- CRITICAL: evidence export bypassed the human-approval gate entirely
  (including with no run at all). Export now requires a per-run, named
  approval recorded into the packet; control lives in Evidence (synced
  with the Counterfactual checkbox, which alone no longer implies export).
- Counterfactual "Rerun simulation" button and all three sliders had lost
  their handlers in a rewrite — restored (sliders re-run debounced).
- Scenario switching desynchronised Studio/Create/CF state (stale runs in
  exports, wrong dropdowns). Single resetRunState on every scenario change.
- Inspector claimed "metres (calibrated)" for pixel-space SAM scenes; now
  branches honestly. Studio scrub range adapts to custom-scene duration.
- Create Lab pointerup duplicated waypoints after selecting one; pointer
  capture + drag guard fixed. SAM captures reset per file (was mixing media).
- Dead skip link rebuilt (hidden until focus, focuses hero heading);
  sidebar dead whitespace removed (sits under header); evidence HTML
  nesting repaired; tiles/footer are real buttons; aria-current="page".

## Tracked, not yet done
- Model endpoints rely on quota, not auth (add FRONTIERSIGHT_API_TOKEN if
  the demo is ever cost-sensitive); durable server persistence for runs;
  SAM full raster decode via meta-sam-parser; per-stage retry policy.
