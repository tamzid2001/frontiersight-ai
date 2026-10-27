# FrontierSight AI

**From video to verifiable physical-world intelligence.**

Built for the **Meta Global AI Developer Hackathon 2026** — Startup Track,
Theme 2: *Push the Frontier*. Owner: Quantura Studio.

> Video models can tell you a forklift "nearly hit" a pedestrian. FrontierSight
> makes them prove it: SAM 3.1 sees, Muse Spark reasons, and an independent
> deterministic physics engine decides — with a human approving the evidence
> before it leaves the building.

**Live demo:** https://frontiersight-ai.vercel.app · **Repo:** https://github.com/tamzid2001/frontiersight-ai

## Run it locally (one command, no keys needed)

```bash
python3 -m pytest -q                                   # 17 tests, offline
PYTHONPATH=. python3 -m services.api.server --port 8000   # → http://127.0.0.1:8000
```

No `MODEL_API_KEY`? The whole demo runs in honestly-labelled `FIXTURE_REPLAY`
mode: no segmentation or model call is claimed. Add the key (server-side only,
see `.env.example`) and Muse Spark hypotheses/narration, SAM 3.1 segmentation
and Muse Image illustrations go live — the deterministic verdicts do not change.

## What it does

1. **Observe** — SAM 3.1 segments/tracks forklifts, pedestrians, robots
   (documented special-token wire format, parsed in `integrations/meta/sam.py`).
2. **Extract** — tracks become timestamped scenes with coordinate frames, units,
   calibration, occlusion windows and provenance per observation.
3. **Verify** — closest-approach, exact-quadratic TTC, continuity/identity-switch
   diagnostics. Uncalibrated video stays in pixel space; metric claims are
   refused, not faked.
4. **Counterfact** — Muse Spark proposes an intervention (strict JSON, schema
   validated); a seeded braking simulation reruns the world with Monte-Carlo
   intervals and a hash-bound manifest.
5. **Approve & export** — an independent verifier checks the simulation, a human
   approves, and a hash-bound evidence packet separates `MODEL_DERIVED`,
   `DETERMINISTIC`, `FIXTURE`, and `ASSUMPTION` content.

Three synthetic scenarios with separately-held ground truth ship in
`fixtures/` (warehouse near-miss, safe passing, occlusion & uncertainty) —
regenerate them with `python3 scripts/generate_fixtures.py`.

## Evidence, not adjectives

- `docs/LIVE_META_VERIFICATION.md` — real Muse Spark / SAM 3.1 / Muse Image
  calls: models, latencies, token usage, parsed boxes/confidences, and the
  honest zero-match result on primitive synthetic shapes.
- `engine/validation.py` — 7 analytical reference cases (head-on TTC = 4.5 s
  exactly, crossing CPA, delayed braking, invalid-input rejection).
- `docs/HACKATHON_COMPLIANCE.md`, `docs/PRIVATE_RESEARCH_AUDIT.md`,
  `docs/UI_RESEARCH.md` — rules, IP method, and design research.

## Layout

```
engine/            deterministic geometry, kinematics, tracking, uncertainty, counterfactual, validation
agents/            bounded 9-stage workflow (roles, idempotency, approval gate)
integrations/meta/ Muse Spark, SAM 3.1 (+ wire-format parser), Muse Image
services/api/      stdlib HTTP API (local + Vercel serverless)
apps/web/          workbench UI (Home, Workspace, Studio, Inspector, Counterfactual, Agents, Evidence, Settings)
fixtures/          3 synthetic scenarios, ground truth held separate
tests/             engine, SAM parser, workflow, API smoke
```

## Labels we keep separate

`deterministic_fixture_verified` ≠ `meta_api_integration_verified` ≠
`real_video_evaluation_completed` (not yet) ≠ `hardware_validation`
(unavailable). **No physical safety certification is claimed.** See
`LIMITATIONS.md`.

MIT — original work, written for this hackathon. See
`docs/PRIVATE_RESEARCH_AUDIT.md` for how prior private research informed
concepts without any code being copied.
