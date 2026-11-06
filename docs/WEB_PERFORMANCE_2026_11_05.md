# Homepage and Lighthouse reliability — November 5, 2026

## Scope
This change is isolated from the uncommitted Create Lab/robot import redesign. It preserves current routes, content, scene schemas and model behavior. The existing lazy MCP-catalog change is applied independently so the homepage does not download and lay out the expanded tool catalog. Settings fetches the real catalog on demand and permits retry after failure.

The original YouTube poster remains the JPEG fallback. A responsive WebP source uses the same owned video and its existing thumbnail URLs. Both endpoints returned200 during verification; the maximum-resolution WebP response was101,388 bytes versus the prior Lighthouse JPEG transfer of approximately220KiB. This is a response-size measurement, not a claimed end-to-end speedup. Intrinsic1280x720 dimensions, meaningful alt text, eager hero discovery and the play control remain.

## Measurement policy
The previous single-run Lighthouse gate varied:81,100 and93 on unchanged code locally. The new workflow always collects exactly three13.6.0 reports with standard throttled mobile emulation. It applies the90 performance threshold to the median; every individual run must still meet95 for accessibility, best practices, SEO and additional scored categories. There is no retry-until-green or optimistic maximum selection. No scores are rounded upward for acceptance.

All raw reports and the aggregate summary are retained, including failed batches. Missing reports, runtime errors, missing network evidence, inconsistent URL/version, invalid scores and hidden editor dependencies fail. The existing request assertions apply to every run. The server readiness check is now a required successful health request. CI also tests this gate and requires nonempty executed Cobertura with90% line and70% branch thresholds.

This changes the aggregation method explicitly; the numerical90/95 thresholds remain. Lighthouse recommends repeated measurements to reduce timing variance: https://github.com/GoogleChrome/lighthouse/blob/main/docs/variability.md and https://github.com/GoogleChrome/lighthouse-ci/blob/main/docs/configuration.md .

## Local verification
- Gate behavior:23 tests passed;97% combined coverage, measured Cobertura.
- Main-based repair regression:318 Python tests passed,22 explicitly skipped;30 Node tests passed. The earlier feature-branch baseline was321/23 skips and35 Node tests; its unfinished editor changes are outside this repair.
- Three local homepage runs after the poster change:96,93,89 performance, median93; all other scored categories100. These were collected on the development machine; timing is variable and no production speedup is claimed.
- Browser checks at390 and1440 pixels selected the genuine WebP thumbnail, retained16:9 display, had no horizontal overflow or uncaught page errors, and the play control opened the correct video embed.
- No GPU, camera, physical robot or paid model execution is part of this validation. Production deployment remains unavailable while the Vercel team is suspended; this does not authorize a paid upgrade.
