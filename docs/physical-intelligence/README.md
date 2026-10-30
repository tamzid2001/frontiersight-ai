# Physical Intelligence v2

The website, `services.api.physical.execute`, HTTP `/api/v2/*`, MCP analysis
and local prediction runtime use one Python implementation. Existing planar
Create Lab/Studio/Counterfactual endpoints remain v1-compatible.

## Run the working software demonstrations

```sh
python -m pip install -e '.[dev]'
python -m services.api.server --port 8000
# Open http://127.0.0.1:8000/physical-intelligence
PYTHONPATH=. python scripts/physical_demo.py --demo warehouse --variant unsafe --out /tmp/unsafe-lift.json
PYTHONPATH=. python scripts/physical_demo.py --demo warehouse --variant earlier --out /tmp/earlier-lift.json
PYTHONPATH=. python scripts/physical_demo.py --demo warehouse --variant faster --out /tmp/faster-lift.json
PYTHONPATH=. python scripts/physical_demo.py --demo warehouse --variant elevated --out /tmp/elevated-load.json
PYTHONPATH=. python scripts/physical_demo.py --demo flying --variant grounded --out /tmp/flight-comparison.json
```

The warehouse approaches using a C2 quintic path, stops, then raises a fork
carriage relative to its chassis. An explicitly attached pallet follows the
forks. Editing a target/start/speed recomputes poses and geometric interactions.
The chassis does not rise. The unsafe-height variant contacts the overhead beam.
**Pallet release/placement, load tipping and structural stability are not modeled.**
The flight example is explicitly hypothetical, with idealized thrust balancing
gravity. It demonstrates independent vertical motion, not real flight feasibility.

The viewport renders returned samples; it does not implement physics in JS.
Top/side/front/perspective views, timeline, component XYZ/quaternion editing,
3D timed waypoints, profile/shape/joint editors, baseline comparison and evidence
are available. Green wireframes show baseline geometry. Current transform editing
is numerical; a 3D drag gizmo is not implemented.

## Contracts and API/MCP

```sh
curl -s https://frontiersight-ai.vercel.app/api/v2/capabilities
curl -s -X POST https://frontiersight-ai.vercel.app/api/v2/scenes/demo \
  -H 'Content-Type: application/json' -d '{"demo":"warehouse"}'
```

POST `/api/v2/scenes/prepare`, `/simulations/run`, `/counterfactuals/compare`,
`/physics/validate`, `/tracks/estimate`, `/tracks/extract`, `/tracks/assumed-scene`,
`/calibration/project`, `/scenes/upgrade` and `/evidence/export` are bounded,
non-persisting deterministic operations. Full request schemas are in OpenAPI 3.1.
`/api/v2` is an additive version. GET `/capabilities` reports actual software scope.

MCP tools include `get_scene_3d`, `prepare_scene_3d`, `simulate_scene_3d`,
`simulate_counterfactual_3d`, `validate_physics_profile`, `estimate_kinematics_3d`,
`calibrate_scene`, `extract_video_tracks`, `tracks_to_assumed_scene_3d`,
`upgrade_planar_scene`, and `export_evidence_packet_3d`. They run without model
credentials or hardware. The stdio bridge uses those same handlers.

Authenticated v1 `create_scenes`/`update_scenes` accept v1 or v2 canonical scenes.
Exact v2 payloads survive Firestore JSON storage, workspace reopen and export.
`propose_physics_profile` / POST `/api/v1/physics/propose` is separate: paid
Clerk workspace, model key, quota and durable idempotency receipt required. A
single 20-second Muse call returns a typed proposal, missing parameters and
assumptions. It never applies it. The UI requires approval, rejects a proposal
after a scene revision, and blocks apply when parameters remain unresolved.
No arbitrary code, dynamic physics imports or actuator calls exist.

```python
from sdk.frontiersight import FrontierSight
api = FrontierSight(token='')  # public deterministic operations only
scene = api.call('scenes/demo', {'demo': 'flying'}, api_version='v2')['scene']
result = api.call('simulations/run', {'scene': scene}, api_version='v2')
```

Regenerate contracts: `PYTHONPATH=. python scripts/build_physical_contract.py`.
Regenerate served guide: `PYTHONPATH=. python scripts/build_api_guide.py`.

## Physics and geometry reference

- SI units; right-handed world ENU: X east/lateral, Y north/longitudinal, Z up.
  Pose positions are **collision-shape centres**, not ground contact points.
  Quaternions are unit **w,x,y,z**. Angular velocities are body-frame rad/s.
  Child poses are relative to parents; parents precede children; cycles rejected.
  Prismatic joints move along upright parent +Z. Rotating articulated parents
  are rejected in this version. Body angular velocity is prescribed; this is
  not a torque/inertia dynamics solver.
- Fixed steps 0.01–0.25 s, horizon ≤30 s, ≤600 steps, ≤16 bodies and ≤50,000 pair
  intervals. Non-finite values, impossible initial speed, actuator/waypoint
  violations and unsupported fields/models fail. Same document → same result.
- Constant acceleration integrates `p+v*dt+0.5*a*dt²` below speed caps. Ballistic
  and hypothetical flight apply gravity, thrust/mass and optional linear drag.
  Vertical speed saturation integrates exactly to the cap. Horizontal capped
  turning and drag use a bounded step approximation; convergence must be checked
  for a new workload. Reported free-body acceleration is the interval mean of
  the actual constrained velocity change; the initial free-body sample is an
  unavailable zero sentinel. Waypoint acceleration is analytic; articulated
  centre kinematics use finite differences. Ground objects retain floor contact. Static fixtures are
  anchored. Mass/inertia/friction inputs do not imply a full contact solver.
- Rest-to-rest waypoint segments use quintic smoothstep, with analytic maximum
  speed `1.875*distance/T` and acceleration `(10*sqrt(3)/3)*distance/T²`.
  Triangular/trapezoidal prismatic lift uses analytic acceleration/cruise/brake
  timing. Payload capacity/elevated-load speed are declared constraints only.
- Sphere/sphere, sphere/OBB and capsule/capsule distances are exact. OBB overlap
  uses 15-axis SAT; positive SAT separation is a **distance lower bound**. Other
  capsule/box queries use enclosing bounds. Compound bodies are explicit child
  shapes, with collision exclusions recorded in the source/evidence.
- Continuous linear sphere and unrotated AABB contact tests are exact. Other
  intervals use conservative swept bounds with acceleration/rotation/error
  inflation: `POSSIBLE_CONTACT` is not a confirmed impact. `CONTACT` is exact
  for the supported geometry/motion, conditional on declared scene inputs.
  Pair clearance minima are **sampled-frame minima** (with separate swept contact
  markers), not an exact global optimization of every curved trajectory.
- Collision response, deformation, fluid dynamics, tipping, validated automotive
  control and safety certification are absent. Predicted contacts do not bounce,
  stop or attach bodies automatically. No Monte Carlo quantiles are fabricated.

## Calibration and tracking

SAM sees masks/boxes, not metric depth. Frame indices are joined to actual decoded
presentation timestamps, never `index/assumed_fps`. Alpha-beta filtering uses each
actual dt, resets on long gaps/identity discontinuity and reports apparent motion
when camera movement is unresolved. Confidence remains provider confidence;
spatial error is a separately declared bound, not an empirical confidence interval.

`calibrate_scene` accepts rectified pinhole intrinsics, explicit camera-to-ENU
pose and supplied optical-axis depth; or intersects a ray with a declared world
horizontal plane. No calibration → `DEPTH_UNAVAILABLE`. A declared plane/scale
→ `ASSUMPTION_3D`; uncertainty-bearing supplied estimates → `ESTIMATED_3D`.
A declared sensor method and evidence identifier can carry
`CALIBRATED_METRIC_3D`; **the application does not authenticate a submitted
calibration certificate or independently validate a sensor**. First-order pixel
and depth error excludes unprovided camera/extrinsic errors. Do not interpret
that label as an audited metrology certificate.

Track conversion explicitly assumes scale, radius and constant height. Endpoint
times more than one second apart are rejected; smaller differences are extrapolated
with an expanded declared error. Original videos and pixel observations remain
separate. The 2D upgrade preserves the original document and makes an explicitly
assumed initial-state tangent prediction; it does not relabel the full old curved
path/delay playback as a measured 3D trajectory.

## Evidence and measurements

`BENCHMARKS.json` contains actual local CPU timings and raw samples, platform,
source digests, frame/body counts and separately measured Python allocation peak.
It is not a camera, model, GPU or robot benchmark. Run:

```sh
PYTHONPATH=. python scripts/benchmark_physical.py --runs 10 --out /tmp/benchmark.json
```

See `VALIDATION.md`, `EDGE.md`, `REFERENCES.md` and the raw Cobertura artifact.
