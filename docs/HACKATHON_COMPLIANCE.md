# Hackathon compliance — Meta Global AI Developer Hackathon 2026

Researched 2026-10-27 from official sources. Where a page did not state a rule,
this document says so rather than assuming it.

## Verified requirements (with sources)
- Event: virtual, 10 days, $1M prize pool; **Track 1 Indie** (creativity, technical
  ambition, functionality) and **Track 2 Startup** (technical execution, production
  readiness). FrontierSight is entered as **Startup Track**. Two themes; we use
  **Theme 2 — Push the Frontier**. Source: https://dev.meta.ai/events/global-hackathon
- Key dates (ET): applications closed Oct 25, 2026 11:59 PM; hackathon Oct 26;
  **project submissions due Nov 4, 2026, 9:00 PM ET**; judging Nov 4–8; winners
  Nov 9. Source: https://dev.meta.ai/events/global-hackathon
- Judging weights (from the participant waiver): **Impact 30%, Use of Meta AI
  Tooling 25%, Demo 25%, Technical Depth & Execution 20%.**
  Source: https://cerebralvalley.ai/e/meta-ai-developer-hackathon/waiver
- Eligibility exclusions include sanctioned regions (Belarus, China, Russia,
  Ukraine, Syria, Cuba, Iran, North Korea, Crimea/Donetsk/Luhansk), Meta/Cerebral
  Valley employees and households, and (waiver) participants must be 18+.
  Sources: event page + waiver above.
- Models offered: Muse Spark series, Muse Image, SAM 3.1 via Meta Model API,
  base URL `https://api.meta.ai/v1`, auth `MODEL_API_KEY`. Sources:
  https://dev.meta.ai/events/global-hackathon, https://dev.meta.ai/docs/overview,
  https://dev.meta.ai/docs/quickstart
- IP: the waiver states the entrant retains ownership of the Submission and
  warrants it is their original work product not violating others' rights, and
  grants the organizers a license to use the Submission. Sources: waiver above.
  Explicit pre-existing-code rules were **not stated** on the fetched event/docs
  pages; the closest verified text is the originality warranty.

## Pre-existing work vs. hackathon work
- **Pre-existing (before Oct 26, 2026):** the author's private research portfolio
  (audited in `docs/PRIVATE_RESEARCH_AUDIT.md`) exploring TTC/closest-approach
  checks, approval ledgers, and evaluation scaffolding. Also the author's public
  `sceneproof` prototype (created during this hackathon window, Oct 27).
- **Independently implemented for this submission (Oct 27, 2026):** every file in
  this repository — engine, agents, Meta integrations, UI, tests, fixtures, docs —
  written from scratch for FrontierSight. No private source files, tests,
  fixtures, history, or assets were copied (see audit doc for the IP method).
- **Licenses:** this repo is MIT (original work). Meta model outputs are used
  via the author's own API key under Meta's terms. No third-party code or
  datasets are bundled; runtime dependencies: none (Python stdlib); dev: pytest.

## Remaining uncertainties
- Whether the author's participant application was accepted (applications closed
  Oct 25) — **formal submission is only possible if selected**. This repo is
  prepared so submission is a form-fill away; it has NOT been officially
  submitted until the portal confirms it.
- Demo video format/length requirements were not stated on fetched pages;
  `docs/DEMO_SCRIPT.md` targets ~90 seconds per the mission brief.
- Waiver page renders client-side; items sourced from it should be re-checked
  against the rendered page before final submission.
