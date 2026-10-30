# Executed validation — 2026-10-30

**317 Python tests passed**, including actual local HTTP/MCP/SDK calls and real
Firestore-emulator tests. **30 Node helper tests passed**. JavaScript module syntax,
OpenAPI 3.1 (65 paths), generated-contract drift and whitespace checks passed.

Application Python coverage: **90.61% lines / 75.41% branches**, 62 first-party
files. Changed production executable lines versus baseline `06e29d9`: **1,302 of
1,421 covered (91.63%)**. Raw Cobertura/LCOV artifacts are in `coverage/` and CI.
Scope: engine, agents, integrations, services, edge and SDK. Tests, developer
scripts, generated OpenAPI/HTML, vendor libraries and browser DOM execution are
not included in that percentage. Optional native camera/ROS entry paths remain
in the report with their real uncovered lines; they are not silently excluded.
Node helpers have their own scoped 99.22% line / 95.65% branch LCOV result; that
is **not whole-browser application coverage**.

The prior baseline had 246 passing tests. Twelve legacy SQLite fixture cleanup
ResourceWarnings persist; no test failure is suppressed. Provider fixtures exercise
software behavior only, not live model quality or hardware performance.

## Commands executed

```sh
FIRESTORE_EMULATOR_HOST=127.0.0.1:56654 python -m pytest -q \
  --cov=. --cov-config=.coveragerc.physical --cov-branch \
  --cov-report=xml:coverage/physical-release-all.xml \
  --cov-report=lcov:coverage/physical-release-all.lcov
python scripts/check_physical_coverage.py coverage/physical-release-all.xml \
  --base 06e29d95902c0a4f125153259bd435cd3721cd6b
node --test --experimental-test-coverage \
  --test-coverage-lines=90 --test-coverage-branches=70 --test-coverage-functions=90 \
  --test-reporter=spec --test-reporter=lcov \
  --test-reporter-destination=stdout \
  --test-reporter-destination=coverage/web-scenes.lcov \
  --test-coverage-include='apps/web/*core.mjs' \
  --test-coverage-include='apps/web/*core.js' \
  --test-coverage-include='apps/web/entity-scale.mjs' tests/*.test.mjs
node --check apps/web/physical-intelligence.mjs
node --check apps/web/edge-studio.mjs
node --check apps/web/app.js
PYTHONPATH=. python scripts/build_physical_contract.py
PYTHONPATH=. python scripts/benchmark_physical.py --runs 10 --out /tmp/benchmark.json
PYTHONPATH=. python scripts/physical_demo.py --demo warehouse --variant unsafe --out /tmp/unsafe.json
PYTHONPATH=. python scripts/make_video_replay.py /tmp/replay.mp4
python -m edge.runtime --source file --input /tmp/replay.mp4 --output /tmp/live.json --max-frames 4
docker compose -f compose.edge.yml config --quiet
```

Local environment: macOS ARM64, Python 3.14.2, PyAV 19.0.2, OpenCV 4.14.0.94,
Node 24, real local Firestore emulator 1.20.2. CI separately validates Linux/Python
3.12 and builds/runs the non-root edge container; refer to the actual workflow
result, not this local record, for container validation status.

## Acceptance evidence

| Demonstration | Actual status |
|---|---|
| Video | Browser upload of generated H.264 completed; 8 actual decoded frames, variable PTS, codec/resolution/duration shown. Inspect mode correctly produced zero tracks. SAM track extraction, multiple concepts, upload/cleanup and failure handling tested with provider fixtures. **Live industrial-video/SAM evaluation NOT RUN: usable local provider credentials unavailable.** |
| Independent forklift lift | Software verified: smooth ground approach, stationary chassis height, relative fork actuator and attached payload; earlier/faster/beam/elevated variants recompute. Unsafe lift produced 4 contact/possible-contact events versus 0 baseline. Payload release/placement remains unimplemented. |
| Hypothetical flight | Software verified: XYZ ascent, speed cap, orientation, true 3D separation from a ground actor; grounded counterfactual collides. No aerodynamic/manufacturer claim. |
| Language physics | One-shot typed proposal and revision/approval gate implemented; provider fixtures verified, **new live model execution NOT RUN**. Backend never applies a proposal or reaches a controller. |
| Camera/live | Actual file decoding, bounded acquisition/replay, freshness/latency and durable worker ran. Reconnect/backoff decisions unit-tested with explicit software fixtures. **USB/RTSP physical tests NOT RUN — CAMERA UNAVAILABLE.** |
| ROS 2 | Structured pose/risk/freshness conversion tested. Executable Jazzy publisher, **NOT RUN — ROS 2 UNAVAILABLE**. No actuator publisher. |
| API/MCP | Actual local HTTP and MCP and SDK produced identical deterministic results. Input/output contracts validated; saved v2 scenes/profile isolation tested with Firestore emulator. |
| Scientific honesty | Invalid depth/calibration/time ordering rejected; assumptions and model confidence distinct; conservative contacts labeled; stale predictions withheld; no simulated result presented as a physical measurement. |

## Remaining scope

This release **does not complete the entire long-term vision**. Independent 6-DOF
force/torque/contact dynamics, arbitrary arm joints, depth/multi-camera fusion,
trained uncertainty distributions, 3D drag gizmos, hosted durable video workers,
Jetson/GPU benchmarks and physical commissioning remain outside the verified
implementation. Software unit fixtures are never substituted for camera/model/
ROS/hardware validation.

Production activation also needs FrontierSight DNS records and restricted
Firestore runtime credentials. Existing Quantura user data/billing is not reused.
No paid compute, cloud resource, IAM grant or physical actuation was created.

Release packaging checks built a wheel and imported its SDK with Python isolated mode
from `/tmp`, outside the checkout. The Linux edge container built and passed its
authenticated no-actuation health check on GitHub Actions. An initial Lighthouse
performance score of 88 failed the preserved 90 gate; the new hidden workbenches
were moved to on-demand loading. Final CI results are recorded by the release PR.
