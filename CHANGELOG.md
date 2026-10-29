# Changelog

## 2026-10-29 — bounded scene candidates and human proportions

- Choose 1–8 parallel candidates, display one scene, and stop without automatic retries.
- Add cancellation, shared deadlines, bounded response reads and process backpressure.
- Preserve edits against late generation results and render model text safely.
- Cap illustrative human heights independently of collision clearance in all 3D viewers.
- Publish the generation API contract and regression tests.

Validation: 176 Python tests passed, 6 optional integration tests skipped;
26 Node tests passed. Web helper coverage: 99.09% lines, 95.65% branches.
