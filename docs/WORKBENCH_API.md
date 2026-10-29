# FrontierSightAI workbench API and MCP

Version 0.38.0. Base URL: `https://frontiersight-ai.vercel.app`.
The machine-readable contract is [OpenAPI](https://frontiersight-ai.vercel.app/openapi.json).
The website, REST and authenticated MCP tools share the same simulation document,
workspace identity and storage operations. No endpoint actuates a physical robot.

## Connect an agent

Sign in at `/settings`, switch to your personal workspace, and create an agent
key. Choose read access, optionally write/model, and copy the one-time value.
Store it in a local secret environment variable, not a URL or source file.
Keys expire within 90 days (the UI uses 30), can be revoked in Settings, and are
stored only as SHA-256 digests. Creating/revoking keys requires a Clerk session;
an agent key cannot mint another key or open billing. Personal keys never grant
organization access. Organization clients use an active Clerk session JWT.

```json
{
  "mcpServers": {
    "frontiersight": {
      "url": "https://frontiersight-ai.vercel.app/api/mcp",
      "headers": {"Authorization": "Bearer <your-private-agent-key>"}
    }
  }
}
```

Use a client that supports secure header configuration. This is Bearer
integration, not an OAuth authorization server; a connector that requires OAuth
cannot use this configuration unchanged. Never share a configured token file.

Browser clients can get a short-lived token with `await Clerk.session.getToken()`.
Refresh it on expiry. The server verifies issuer, authorized party, signature,
expiry, subject, and active organization. User IDs and plan names in JSON never
authenticate a caller. An optional `X-Workspace-Organization` header (org ID or
`personal`) rejects replies/writes from a stale workspace selection.

## REST

Private operations are POST JSON under `/api/v1`. Include
`Authorization: Bearer …`. List/get use POST to keep private identifiers out of
URLs. `/api/v1/account` is GET. Request bodies are limited to 350KB; scene and
stored-result JSON is limited to 256KiB. Errors use appropriate 400/401/402/403/
404/409/413/415/429/502/503 statuses, without provider secrets.

| Resource | Endpoints | Inputs / result |
|---|---|---|
| Scenes | `/scenes/create`, `/list`, `/get`, `/update`, `/delete` | `name`, `scene`; get/delete: `id`; update/delete: `expectedVersion`. Returns ID/version; get/list return records. |
| Objects | `/objects/validate`, `/generate`, `/create`, `/list`, `/get`, `/update`, `/delete` | Generate: description/model; save: name/spec; a spec is a bounded parts recipe, not an arbitrary executable mesh. |
| Reuse | `/objects/use` | `scene`, `object_record_id`, new unique `object_id`, `x`, `y` in metres. Returns new unsaved scene with the exact saved recipe. |
| Route | `/paths/plan` | `scene`, moving `object_id`, `goal:[x,y]`; optional resolution/clearance/smooth. |
| Prediction | `/paths/predict` | `points:[[t,x,y],…]`, horizon/step, declared space and optional metre-space stage/radius. |
| Describe paths | `/paths/describe` | `scene`, `description`, optional approved Muse `model`. Existing exact object IDs only. |
| Scene generation | `/scenes/generate` | description/model, candidates 1–8 (default 3); one selected scene then stop. |
| Playback | `/scenes/prepare` | scene; returns floor dimensions, object definitions, timestamped tracks and digest used by Studio/Counterfactual. |
| Media library | `/media/create`, `/list`, `/get`, `/update`, `/delete` | Frame: name/kind=frame/data_url/timestamp_s/optional source_video_id. Video: name/kind=video/provider_file_id. |
| Segmentation | `/media/segment-frame`, `/media/segment-video` | owned media_id, concept; Meta SAM provider checks its own file access. |
| Export a frame | `/media/render-frame` | scene, timestamp_s, width/height; real PNG data URL plus exact simulated metre-space poses. |
| Export animation | `/media/render-preview` | scene, duration_s/fps/width/height; animated GIF, not MP4 or photorealistic 3D video. |
| Model receipt | `/model-requests/get` | original `request_key`; returns running/completed/failed_or_unknown and saved result where available. |
| Provider key | `/provider-key/save`, `/status`, `/delete` | Clerk paid workspace administrator only; save key encrypted at rest, return only last4/status. Model requests use a per-request context, never a shared environment mutation. |
| Agent keys | `/keys/create`, `/keys/list`, `/keys/revoke` | Clerk personal session only; name/scopes/days or ID to revoke. |
| Billing | `/billing/checkout`, `/billing/portal` | personal Clerk session only; period monthly/annual; server-created Stripe URL. |

The abbreviated paths above are relative to `/api/v1`. Every table operation also
has a corresponding MCP tool except key administration and billing, which remain
interactive account operations. Tool names are listed by `tools/list`.

### Example: save, reuse, plan, render

```python
import json, os, uuid, urllib.request
BASE = "https://frontiersight-ai.vercel.app"
def api(path, body, key=None):
    request = urllib.request.Request(BASE + "/api/v1/" + path,
        data=json.dumps(body).encode(), headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + os.environ["FRONTIERSIGHT_API_KEY"],
            "Idempotency-Key": key or str(uuid.uuid4())})
    with urllib.request.urlopen(request, timeout=40) as response:
        return json.load(response)

# A declared metre-space document. Paths and radii must fit the floor.
scene = {"stage_metres": [16,14], "objects": [
    {"id":"robot-7", "category":"robot", "speed":1, "radius":.5,
     "waypoints":[[2,7]], "curve":"straight", "mode":"stop"},
    {"id":"shelf-1", "category":"shelf", "speed":0, "radius":2,
     "waypoints":[[8,7]]}]}
planned = api("paths/plan", {"scene":scene,"object_id":"robot-7","goal":[14,7]})
saved = api("scenes/create", {"name":"Warehouse route","scene":planned["scene"]})
loaded = api("scenes/get", {"id":saved["id"]})["record"]
prepared = api("scenes/prepare", {"scene":loaded["payload"]})
frame = api("media/render-frame", {"scene":loaded["payload"],"timestamp_s":3})
```

A save does not generate another scene, mutate another tenant, or invoke a model.
Create a recipe with `objects/generate`, explicitly save its `spec` with
`objects/create`, then call `objects/use` with that record's ID. Reuse returns a
new scene; explicitly save it if desired. No implicit overwriting occurs.

## Writes, retries and concurrency

Supply a fresh 16–128 character `Idempotency-Key` for each intended mutation or
model invocation. Reuse the same key/body only when recovering that exact request.
Same key/different body returns 409. Updating/deleting a stale `expectedVersion`
returns 409, requiring a fresh read and an explicit user decision.

Model invocations have durable reservations. Completed requests replay the saved
result. Running or failed/uncertain attempts return 409; inspect the receipt,
never automatically send a new key to repeat potentially charged work. Client
cancellation stops waiting; it cannot guarantee provider-side cancellation.

## Geometry and prediction semantics

A* uses an eight-neighbor bounded planar grid and radius-inflated static circular
footprints. It validates line segments; smoothing is retained only if its sampled
curve passes the same geometry checks. It does not reserve moving actors, solve
robot joint constraints or certify a safe physical trajectory. Run analysis for
moving interactions. It can reject a route because of resolution/work limits.

Prediction is a least-squares constant-velocity fit over the most recent 20 of
3–5,000 strictly ordered timestamped positions. Returned forecast points remain
separate from observations. The optional floor-constrained display trajectory
holds at a boundary; that is not predicted braking. Residual RMSE is not a calibrated
uncertainty interval. Pixel predictions are not metres without calibration.
Applying predicted geometry in Create Lab uses the component's acceleration and
turn limits for playback, so playback timing can differ from extrapolation.

Language edits use one Muse request (20-second socket timeout, no repair/retries).
Unknown/repeated IDs, invalid settings or out-of-floor sampled curves are rejected
before changing the scene. Browser revision guards discard stale replies.

## Media limits

Saved frames: valid JPEG/PNG, <=180,000 data-URL characters, <=4 million pixels.
Frame timestamps are source-video seconds. A source_video_id must belong to the
same workspace. Video segmentation requires your own saved Meta key, so a shared host credential cannot access another tenant's provider file by a guessed ID. Video records reference a file already uploaded to Meta's file
service; this API does not pretend to upload gigabytes into Firestore or accept
arbitrary URL fetches with server credentials. Browser frame extraction remains
available for local videos. Provider files have their own retention/access policy.

PNG exports are top-down 2D simulation illustrations. GIF previews are bounded to
60 frames / 20 million aggregate pixels / 2MB encoded output. GIF centisecond
quantization is reported in the response; it is not falsely described as exact
arbitrary-FPS MP4. WebGL 3D renderers are separate browser capabilities.

## MCP protocol

Stateless JSON Streamable HTTP at `/api/mcp`; initialize negotiates a supported
protocol (2024-11-05 compatibility, 2025-03-26, 2025-06-18 or 2025-11-25). POST
JSON-RPC, advertise JSON/SSE Accept support, and send the negotiated
`MCP-Protocol-Version` subsequently. Notifications return 202. No unsolicited SSE
stream is offered (GET with SSE Accept returns 405). Origins are checked.

`tools/call` uses the same Workbench.execute dispatcher as REST. Mutating/model
tools take `idempotency_key` in arguments. Failures return `isError`; no background
model loop is started. The original offline stdio bridge exposes analysis only:
private tools return an authentication error and cannot spend host credits.

## Deployment prerequisites and current limitations

Firestore, restricted server credentials, Clerk and an audit secret are required
for durable libraries, agent keys and model receipts. There is no SQLite fallback
for those endpoints. Credentials are never returned in diagnostics. Explorer gets
10 scene records, 12 object recipes, 25 media records, 100 mutations/month per
library; Researcher gets up to 5,000 records and 20,000 mutations/month per library.
Model API requests have an additional 10/minute workspace budget.

Production credentials and live Stripe activation must be configured and verified
before treating a deployment as fully operational. Tests use the real Firestore
emulator and signed test Clerk JWTs; provider calls are fixtures, not measured live
inference. See BILLING_DEPLOYMENT.md and COVERAGE.md for evidence and setup.

## Python helper and stdio-only agent clients

`sdk/frontiersight.py` is a dependency-free client. `FrontierSight` accepts a
private key or a callable that returns a fresh Clerk JWT. Named helpers cover
scene creation/loading, generation, path planning/prediction/descriptions, saving
and reusing objects, rendering and receipt lookup. `call("resource/operation",
body, request_key=...)` covers the remaining published operations. It validates
the origin, supports HTTPS (HTTP only for localhost), and never automatically
retries a potentially charged request. Save `client.last_request_key` after an uncertain request to inspect/recover it. For concurrent use, explicitly assign and retain a separate request_key per operation.

For an agent that supports stdio but not HTTP headers:

```bash
# Set FRONTIERSIGHT_API_KEY in your local secret manager, not shell history.
python3 scripts/mcp_stdio.py --url https://frontiersight-ai.vercel.app/api/mcp
```

Without `--url`, this command remains offline. Remote failures emit a JSON-RPC
error without printing credentials, upstream bodies or making a second request.

Saved Meta credentials apply to authenticated workbench generation, path edits and segmentation; paid Create Lab scene generation uses that same API when cloud workspace saving is enabled. Legacy guest demo requests use the host fair-use key. Candidate worker threads inherit only their own request context.

The local key registry bounds each account to 10 active keys and 100 retained key records. Operators must purge expired/revoked history according to their retention policy before that history cap is reached; expiry alone is not a Firestore TTL deletion.
