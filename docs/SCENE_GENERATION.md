# Scene generation and illustrative entity scale

`POST /api/meta/scene` accepts `prompt`, an optional supported `model`, and
`candidates` (integer 1–8, default 3). Candidate requests run in parallel and
share a 28-second provider deadline. Each candidate makes exactly one provider
request, with no automatic retries or second repair prompt. A heuristic selects
one validated scene, favoring fewer path-quality issues and a close interaction.
This ranking is not a safety certification or an accuracy benchmark.

The response reports requested/completed/valid candidates, selected index,
provider identity, deadline and zero automatic retries. Invalid candidates are
ignored; an entirely invalid batch fails without modifying the scene. At the
deadline a completed valid candidate can be selected while slow peers finish
remotely. Only one batch per process can own provider capacity. Pending calls
retain that capacity even after a timeout; subsequent requests receive 503.

The browser disables repeated submissions, offers cancellation and stops waiting
after 35 seconds. It ignores late results and results produced while the user
edited their scene or prompt. Cancellation cannot guarantee that an already sent
provider request stops or avoids billing. Increasing candidates increases usage.

OpenAPI: `/openapi.json`. MCP: `/api/mcp` retains deterministic tools; it does not
expose model generation or permit agents to trigger unbounded model spending.

Pedestrian meshes are capped at an illustrative 1.85 m height (cyclists: 1.8 m),
while fitting inside the declared planar collision radius. Changing a collision
clearance no longer stretches a human vertically. This is visual-only: collision
radii, physical paths and deterministic analysis are unchanged.

Validation: `python -m pytest -q`; `node --test tests/*.test.mjs`.
Tests use bounded local fixtures, not paid inference or simulated GPU evidence.
