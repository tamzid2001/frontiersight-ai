# Limitations (honest, by design)

- Demo scenarios are synthetic fixtures with known ground truth; they validate
  the pipeline on synthetic data only — not performance on real industrial video.
- SAM 3.1 video *tracking* on real footage is integrated at the documented API
  level but not yet benchmarked end-to-end (label: real_video_evaluation_completed = false).
- Mask payloads are parsed for boxes/ids/confidences/headers; full raster
  decoding is delegated to Meta's `meta-sam-parser` (documented in sam.py).
- 2D planar physics (3D view is visualisation only). Path motion uses per-category
  dynamics (acceleration, lateral-g in curves, minimum turn radius — declared in
  `engine/curves.py:DYNAMICS`) with start/stop ramps; CPA/TTC remains a
  constant-velocity *prediction* shown next to measured along-path proximity.
  No 3D reconstruction unless
  calibration supports it; pixel-space results when uncalibrated.
- No physical safety certification is claimed or implied. Counterfactuals are
  conditional predictions under declared assumptions.
- In-memory job/checkpoint store in this deployment tier; durable multi-tenant
  persistence (Postgres/object storage) is future work, not present.
