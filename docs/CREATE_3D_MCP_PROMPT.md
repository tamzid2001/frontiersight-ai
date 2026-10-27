# The perfect upgrade prompt — Create Lab 2D/3D + MCP server

> This is the prompt that was executed for the 0.21.0 upgrade. It is kept in
> the repo as the binding spec; implementation notes follow it.

---

**You are a senior creative-technologist and API designer upgrading
FrontierSight AI's Create Lab. Deliver two things, production-grade and
verified in a real browser, without breaking anything that works.**

## Part 1 — 2D/3D scene authoring in Create Lab

Users currently author scenes on a 2D top-down stage (waypoints, straight or
Catmull-Rom curved paths, per-component speed/radius/delay/mode). Add a **3D
view of the same scene** — not a separate editor with separate state.

Decisions already made (do not relitigate; implement them well):

- **Three.js r160, vendored** (`apps/web/vendor/`, MIT licence file included),
  loaded as ES modules behind an import map. No bundler, no CDN at runtime:
  the app must keep working offline and on Vercel's static file serving.
  OrbitControls from the same vendored copy. Lazy-initialise on first 3D open.
- **One source of truth:** `state.lab.objects`. The 3D view renders exactly
  what the 2D canvas renders — same resolved paths (straight and curved),
  same preview clock, same selection state. Toggling 2D/3D never loses work.
- **Entities, not boxes:** build each category from primitives in the same
  realistic palette as the 2D sprites — forklift (body, mast, forks, wheels),
  pedestrian (legs/torso/head), robot (body + lidar dome), vehicle (body +
  cabin + wheels), cyclist (wheels + frame + rider), shelf (rack + bays) —
  correctly oriented to path heading, sitting on a 16×14 m ground grid.
- **Interaction parity where honest:** orbit/pan/zoom; click on the ground
  adds a waypoint to the selected component (raycast to the ground plane,
  click-vs-drag disambiguated); preview play/scrub drives both views.
  Waypoint *dragging* stays a 2D affordance in v1 — say so in the UI.
- **Honesty (non-negotiable, inherited):** 3D is a visualisation of the same
  planar scene model. Heights are illustrative; physics, sampling and
  analysis remain 2D and their assumptions already say so. The UI states
  this next to the toggle. If WebGL is unavailable, show that plainly and
  keep 2D fully functional — never a blank stage.
- **Performance:** rebuild entity groups only when the scene changes
  (waypoints/components), move them per-frame; cap pixel ratio at 2;
  pause rendering when the 3D view or tab is hidden.

## Part 2 — a usable MCP server

Expose FrontierSight's deterministic capabilities as an **MCP server other
agents can actually call**, documented well enough that a user connects in
under two minutes.

- **Transport:** MCP Streamable-HTTP style JSON-RPC at `POST /api/mcp`
  (initialize, ping, tools/list, tools/call; notifications acknowledged),
  plus `GET /api/mcp` returning a human-readable tool catalog. Also ship
  `scripts/mcp_stdio.py`, a stdio bridge with identical behaviour for local
  MCP clients (it runs the same in-process handlers, so it works offline
  against a clone).
- **Tools (deterministic first — this is the point of the product):**
  `list_scenarios`, `get_scenario`, `analyse_scenario` (measured +
  predicted proximity per pair), `analyse_tracks` (user tracks, calibration
  rules enforced), `simulate_counterfactual` (path-following braking sim;
  Explorer Monte-Carlo cap enforced), `sample_paths` (straight/curved path
  sampling), `validate_scene` (the Muse scene schema), `server_info`.
  Every tool has a real JSON input schema, returns structured JSON content,
  and surfaces engine errors as MCP tool errors with the engine's message —
  never a stack trace, never an invented result. Model-backed tools are
  out of scope for MCP v1 (deterministic surface only) — say why in the docs.
- **Docs:** `docs/MCP.md` with copy-paste configs for Claude Code
  (`claude mcp add --transport http …`), Cursor/VS Code `mcp.json`, and the
  stdio bridge; the Settings screen shows the endpoint, its live tool list
  (fetched, not hardcoded), and the same snippets.
- **Safety:** MCP inherits the API's validation, payload bounds and rate
  limits. It cannot create accounts, spend the host's Meta key, or export
  evidence — the human approval gate is a UI/legal boundary, not an API one
  to route around.

## Acceptance criteria

1. In Create Lab, toggling to 3D shows the current scene (curved robot
   patrol visibly curved in 3D) with working orbit controls; adding a
   waypoint by clicking the 3D ground works; play/scrub move entities in
   both views; switching back to 2D loses nothing.
2. A headless-browser audit renders the 3D canvas with non-blank WebGL
   pixels and zero page errors, in both themes.
3. `curl` against `/api/mcp` completes initialize → tools/list →
   tools/call (`analyse_scenario` on warehouse-near-miss) with correct
   JSON-RPC framing; the stdio bridge answers the same sequence offline.
4. All prior audits (unit 60+, main browser flow, billing, workspaces)
   stay green; GitHub + Vercel updated; anything not deliverable is
   reported as an exact blocker, not smoothed over.

**Anti-goals:** no React/Three rewrite of the app, no build step, no
externally-hosted assets at runtime, no 3D physics claims, no MCP tools
that spend money or bypass approvals.

---

## Implementation notes (what was actually built, 0.21.0)

- `apps/web/vendor/three.module.min.js` + `addons/OrbitControls.js` (r160,
  MIT, `THREE-LICENSE.txt` vendored). Import map in `index.html`;
  `apps/web/three-view.js` lazy-initialises on first toggle, raycasts
  ground clicks to waypoints, syncs from `labDraw` (entity rebuild on
  scene change, per-frame poses from `posOnPath`), `devicePixelRatio ≤ 2`,
  renders only while visible. Server serves the vendor files (new
  `.svg/.png/.js` static types already present); Vercel rewrites map the
  two vendor paths through the function with `ep` routing.
- `services/api/mcp.py`: `handle_jsonrpc()` shared by `POST /api/mcp`
  and `scripts/mcp_stdio.py`. Eight deterministic tools as specced;
  engine errors become MCP `isError` tool results with the engine message.
- Settings gained an MCP card (endpoint, fetched tool list, config
  snippets); `docs/MCP.md` documents Claude Code / Cursor / stdio setup.
