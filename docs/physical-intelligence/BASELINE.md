# Physical intelligence baseline — 2026-10-29

Baseline main: `06e29d95902c0a4f125153259bd435cd3721cd6b` (PR #4).
Executed local baseline: **246 passed in 23.30s**, Firestore emulator at
127.0.0.1:56654. Raw log is retained outside Git in the dated site-review log
folder. GitHub Python 3.10/3.12, Firestore integration and Lighthouse checks passed
before merge. Vercel production READY for that exact SHA.

Audited README, ARCHITECTURE, LIMITATIONS, `engine/`, `agents/`, `services/api/`,
`integrations/meta/`, browser workbench, stdio bridge, OpenAPI, CI and deployment.
Existing engine is planar; existing 3D view is illustrative. Existing SAM parser,
Clerk verification, Firestore libraries, request receipts and 2D workflows are
reused. No foreign repository source was copied.

Host: macOS ARM64; no ffmpeg/ffprobe on PATH at baseline. No ROS 2, physical
camera/robot or NVIDIA GPU execution verified. Python coverage tooling and a
real local Firestore emulator are available. No cloud compute was created.

## Bounded milestones

1. Versioned SI/ENU algebra, typed physics, collision and articulated simulation.
2. Analytical reference tests, unsafe-input rejection, regression tests.
3. Canonical REST/MCP contracts, scene persistence compatibility.
4. Warehouse/flying workbench rendered from backend world-state samples.
5. Approved, one-shot language physics proposals; no actuator access.
6. Timestamp-aware SAM extraction and calibration/uncertainty gating.
7. Durable local video worker and bounded upload/replay path.
8. Edge acquisition, stale-state diagnostics, shadow ROS observation bridge.
9. Coverage, reproducible benchmarks, deployment verification and limitations.

No hardware or production-ready status follows merely from completing software
milestones. Each milestone records actual evidence and remaining acceptance gaps.
