# Deep code review #2 — 2026-10-27 (pre-0.7.0)

Scope: all 2,154 lines (engine, agents, integrations, API, web, tests) re-read;
WCAG contrast computed for every text/background token pair; browser audit
re-run. Findings fixed in 0.7.0 unless marked accepted.

## Fixed
1. **[bug, user-facing] Single-observation tracks crashed analysis.**
   `analyse_pair` called `velocity_at` on tracks with <2 points (exactly what
   one SAM frame capture produces) → `IndexError` → HTTP 400. Now returns
   `insufficient observations` with the reason. (`engine/kinematics.py`)
2. **[bug] Duplicate `object_id`s in uploaded tracks silently collided** in
   by-id lookups (counterfactual agent selection). `parse_tracks` now rejects
   duplicates and out-of-range radii. (`services/api/server.py`)
3. **[integrity] Evidence `source_digest` was a hash of the scenario *name*.**
   Now a SHA-256 of the full scenario document. (`services/api/server.py`)
4. **[robustness] Workflow simulation assumed ≥2 points** on the focus pair.
   Zero-velocity guard added. (`agents/workflow.py`)
5. **[a11y] Contrast failures in light theme.** Button text on light cyan was
   3.56:1 and the theme-segmented control was 2.05:1 in dark. Introduced
   `--accent-ink` per theme, darkened light cyan/teal (`#0a6d85` / `#0b7a5f`),
   raised dark `--dim` to `#9db1cc`. All audited pairs now ≥4.5:1.
6. **[ux] Circles → real entities.** All three canvases (Studio, Create Lab,
   Counterfactual map) now draw heading-oriented vector silhouettes with
   realistic colours (amber forklift with mast/forks, hi-vis pedestrian with
   walking-phase legs, lidar robot, vehicle, cyclist, shelf rack), plus
   panel-backed label pills readable over any background in both themes.

## Accepted / documented (not fixed, with reason)
- `Track.velocity_at(_nearest_index)` uses the segment ending nearest the
  window start — documented assumption, consistent across pairs.
- SAM mask payloads remain opaquely retained (decode via `meta-sam-parser`),
  stated in `integrations/meta/sam.py`; boxes/ids/confidences are parsed.
- Rate limiting is per-instance best-effort on serverless; ingest bounds
  (12 MB, validation) are the hard controls.
- `stage().retries` is recorded but stages don't retry internally; retries
  live in the Meta transport (`spark._call`, bounded). Noted for a future
  workflow-level retry policy.

## Typography
System-ui stack with antialiasing, −0.025em display tracking on `h1`,
uppercase 13px section labels, `tabular-nums` for all measured values
(mono, tables, inputs) so columns of numbers align; canvas labels moved to
600-weight pills with theme panel backing instead of raw text on imagery.
