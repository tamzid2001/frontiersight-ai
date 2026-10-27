# UI research → design system

Researched 2026-10-27. Mobbin/Dribbble pages are partially paywalled/JS-gated;
where a shot could not be fully rendered, observations come from public search
surfaces and pattern libraries, and are labelled as such. Patterns were
studied, artwork was not reproduced.

## Grounded references (12+)
1. Dribbble — Industrial IoT Dashboard (shot 27501289, provided by owner): dense
   operational grids, status-first hierarchy → Studio's stage + side inspector.
2. Dribbble — AI Agent Workflow Automation Dashboard (shot 27798940, provided):
   staged agent pipelines with per-step status → Agent Trace screen.
3. Dribbble — Telecom AI Dashboard / Digital Twin UI (shot 27692098): twin
   canvas with overlay telemetry → top-down scene stage with track overlays.
4. Dribbble — AI Agent Orchestration Operations Dashboard (shot 27709802):
   orchestration graphs, retry/attempt affordances → stage cards show retries.
5. Dribbble — AI-Powered Energy Dashboard / Factory Ops (shot 27201877):
   site-breakdown density, amber warning language → event list severity colours.
6. Dribbble IoT/factory monitoring corpus (dribbble.com/tags/iot-dashboard):
   dark graphite panels, cyan analytical overlays → colour tokens below.
7. Mobbin — shipped dashboard flows (mobbin.com/explore/mobile/screens/dashboard):
   3–5 primary metrics before detail → Home hero leads with one demo, not stats.
8. Mobbin — Stripe dashboard screens (mobbin.com): layered detail, status labels
   beside values → Evidence screen labels every number with provenance.
9. Mobbin — log-dashboard corpus (Sentry/Stripe/Cohere screens): filterable
   execution logs → Agent Trace is a structured, attribution-first log.
10. Mobbin glossary — empty states (context + guidance + visual): Studio's
    pre-analysis state explains what running analysis will produce.
11. Mobbin pattern research — pre-flight intro screens (Monzo/Qantas/N26):
    expectations before consequential actions → human-review gate explains
    itself before blocking export.
12. Mobbin MCP announcement (mobbin.com/mcp, 2026): progressive disclosure with
    step indicators → 9-stage workflow is disclosed stage-by-stage, not dumped.
13. Linear/Notion-style contextual side panels (via Mobbin shipped-app corpus):
    inspector beside canvas, list selection drives detail → Studio event list
    seeks the player; Inspector shows frames/units/uncertainty.

## Original design system (implemented in apps/web/app.css)
- **Tokens:** `--bg #080a0e`, panels `#10141c/#0b0f16`, line `#232b3a`, ink
  `#e8edf6`, dim `#8fa0b8`; analytical cyan `#38c6d9`, validated teal `#2dd4a8`,
  warning amber `#f2b04a`, critical red `#f26d7d`. One accent family, red only
  for risk. No decorative gradients beyond a single ambient radial.
- **Typography:** system-ui for prose; `ui-monospace` for measurements, hashes,
  timestamps — numbers should look measured.
- **Components:** pill (status/mode), card, stage card (canvas + transport),
  trace item (left border = status), ev (clickable event row), pill.warn/ok.
- **Motion:** only functional motion — canvas playback, scrub, debounced (350 ms)
  slider reruns. No fake terminal animation, no decorative charts.
- **Accessibility:** labels on every control, `role="status"` on async results,
  colour is never the only signal (events also carry text type + values),
  layout collapses to one column under 900 px.
- **Visual acceptance criteria:** (1) verdict + provenance visible without
  scrolling in Studio; (2) occlusion state differs in dash + text, not colour
  alone; (3) counterfactual chart shows both series labelled; (4) every async
  surface has empty/loading/error copy that tells the truth (e.g.
  BLOCKED_CREDENTIALS, FIXTURE_REPLAY).
