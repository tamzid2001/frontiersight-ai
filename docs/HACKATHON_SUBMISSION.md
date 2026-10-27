# FrontierSight AI — hackathon submission

- **Project:** FrontierSight AI — *From video to verifiable physical-world intelligence.*
- **Owner:** Quantura Studio · **Track:** Startup · **Theme:** Push the Frontier
- **Repo:** https://github.com/tamzid2001/frontiersight-ai
- **Live app:** https://frontiersight-ai.vercel.app
- **Deadline:** Nov 4, 2026, 9:00 PM ET

## Problem
Robotics and warehouse teams increasingly trust video models to say what
happened in a physical scene. Those models produce plausible tracks and
confident summaries — but nobody can replay *why* a near-miss was flagged,
which numbers were measured vs. invented, or whether a proposed fix actually
helps under stated assumptions.

## What FrontierSight does
Upload/footage or a bundled fixture → SAM 3.1 segments and tracks forklifts,
pedestrians, robots → a deterministic engine computes closest approach, TTC,
continuity and occlusion diagnostics → Muse Spark proposes a counterfactual
("slow the forklift 30% at t=0.5s") → a seeded braking simulation reruns the
world with Monte-Carlo intervals → an independent verifier checks the result →
a human approves export of a hash-bound evidence packet that separates
MODEL_DERIVED, DETERMINISTIC, FIXTURE and ASSUMPTION content.

## Why Meta AI is essential
Muse Spark does the reasoning and narration; SAM 3.1 does the seeing;
Muse Image produces clearly-labelled illustrative visuals. Removing Meta's
models removes the perception and hypothesis layer — the deterministic engine
alone cannot interpret new footage. Verified live: see
`docs/LIVE_META_VERIFICATION.md` (real token usage, latencies, SAM boxes and
confidences parsed from the documented wire format).

## Core novelty
Proof-carrying physical AI: an LLM may propose and explain, but every physical
claim is either computed by seeded deterministic code (with analytical
reference cases), or explicitly labelled as model-derived, fixture, or
unsupported assumption. Uncalibrated video stays in pixel space — the system
refuses to fabricate metres.

## Measured evidence
- 17 pytest tests + 7 analytical validation cases (head-on TTC = 4.5 s exactly,
  crossing CPA, delayed-braking, invalid-input rejection…), CI on GitHub.
- Live Meta calls: Muse Spark narration (11.8 s, 2,231 tokens), structured
  hypothesis (7.3 s), SAM 3.1 on an illustrated warehouse frame (object ids 0/1,
  confidences 0.57–0.97, 1.5–1.7 s), Muse Image generation.
- Counterfactual: warehouse near-miss baseline vs. braking intervention
  recomputed per slider input on the server; manifest hash changes with inputs.

## Known limitations
Synthetic fixtures validate the pipeline on synthetic data only; SAM video
tracking on real industrial footage is integrated at the API level but not yet
benchmarked; no safety certification is claimed; metric claims require
declared calibration. Full list: `LIMITATIONS.md`.

## Originality & licence
Written from scratch for this hackathon (Oct 27, 2026) by Quantura Studio;
concepts re-derived from the author's private research without copying code
(`docs/PRIVATE_RESEARCH_AUDIT.md`). MIT licence. Not officially submitted
until the Cerebral Valley portal confirms.
