# FrontierSight physical intelligence progress

Baseline: `06e29d9`, 246 passing tests, planar engine. Working branch:
`feat/physical-intelligence-3d-20261029`.

| Milestone | Evidence / implementation commit |
|---|---|
| SI/ENU primitives, typed 3D bodies, exact/conservative geometry and independent fork/payload lift | `0a69528`; analytical reference tests |
| C2 XYZ waypoints, calibration gating, timestamp-aware tracking, payload constraints | `3b323eb`; negative/boundary/analytical tests |
| Canonical REST/MCP/SDK, 3D browser workbench, approved physics proposals, app-owned profiles | `6cc9e51`; actual HTTP/MCP parity, Firestore emulator |
| Durable local video jobs, upload/resume, actual decoding, shadow runtime/ROS adapter | `185e463`; actual H.264 decode/replay + explicit provider/hardware software fixtures |
| Cancellation ownership, bounded reconnect/result budgets, output schemas, coverage/CI and measured benchmarks | Subsequent release commits; see VALIDATION.md and Git history |

Latest local validation: 317 Python / 30 Node tests passed; application line/branch
coverage 90.61% / 75.41%; changed production lines 91.63%. Raw reports, actual
commands, source hashes and acceptance-status matrix are preserved.

Physical actuation is disabled. Model/camera/ROS/GPU verification and production
Clerk DNS/Firestore credentials remain blocked as documented. No milestone is
marked as physical hardware validation or completion of all product acceptance
criteria. See `docs/physical-intelligence/VALIDATION.md`.

Account reads and sync now use the same app-owned Firestore profile in Firestore mode.
Guest account reads remain backward compatible. Session/scoped-key OpenAPI schemes
are valid. Pending browser requests are invalidated on Clerk workspace changes,
preventing a previous workspace response from restoring private scene state.

The SDK is included in the built distribution and checked outside the source tree.
New 3D/video modules and styles load on demand to preserve homepage performance.
