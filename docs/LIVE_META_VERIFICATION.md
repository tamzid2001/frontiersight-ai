# Live Meta Model API verification — measured, not claimed

Date: 2026-10-27. Key: author's own `MODEL_API_KEY`, server-side only, never logged.
Harness: `scripts/live_meta_check.py` + a Muse Image → SAM chain probe. Reproduce:
`MODEL_API_KEY=… python3 scripts/live_meta_check.py`

| Call | Model | Result | Measured evidence |
|---|---|---|---|
| Narration of deterministic findings | `muse-spark-1.3` | OK | latency 11,826 ms; usage 107 in / 2,124 out tokens (1,970 reasoning); response id `resp_6ae0e2ca…`. Output correctly refused to invent a TTC (input had `ttc_s: null`) and flagged unquantified calibration uncertainty. |
| Structured hypothesis (schema-validated) | `muse-spark-1.3` | OK | latency 7,343 ms; 158 in / 1,301 out tokens. Returned strict JSON: 30% speed reduction at t=0.5s, within our enforced bounds (0–80%, t≥0). |
| SAM segmentation, synthetic block PNG (640×480, sha256 `fa37e7ca…`) | `sam-3.1` | HTTP 200, **zero matches** | latency 445–568 ms. Zero matches is a documented valid outcome; primitive rectangles are not people/forklifts. Recorded as-is. |
| SAM segmentation, Muse Image warehouse illustration (illustrative only, sha256 `e2c9b7a9…`) | `sam-3.1` | HTTP 200, **real records parsed** | "forklift": object ids 0,1 — boxes e.g. x1=1062,y1=660,x2=1547,y2=959 on 1920×1280, confidences 0.942 / 0.566, mask rasters 300×486 / 180×218 (`one_bit`). "person": ids 0,1 — confidences 0.922 / 0.973. Latency 1,462 / 1,691 ms. Parsed by `integrations/meta/sam.py` implementing the documented special-token grammar. |
| Illustrative image generation | `muse-image-1.0` | OK | Returned `b64_json` (WebP). Labelled ILLUSTRATIVE in-product; never used as evidence. |

## Labels (kept separate, per acceptance gates)
- `deterministic_fixture_verified`: YES (17 unit/property tests + 7 analytical validation cases).
- `meta_api_integration_verified`: YES for Muse Spark (narrate + structured hypothesis), SAM 3.1 (transport + wire-format parsing against a real response), Muse Image (generation).
- `real_video_evaluation_completed`: **NO** — SAM video tracking on real industrial footage is not yet evaluated; demo path is synthetic fixture replay.
- `hardware_validation`: unavailable. `production_deployment_verified`: see README live URL + smoke results.
- Cost: token usage recorded above per call; dollar cost not published by the API response, so none is claimed.
