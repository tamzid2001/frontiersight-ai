# Demo video script (~90 seconds)

**0–15s — Problem.** "A warehouse camera sees a forklift pass a pedestrian.
Your video model says 'near miss'. Can it prove it? Which numbers did it
measure — and which did it invent?" Show the Home screen and the provenance
promise.

**15–35s — Observe.** Open the Studio, load *warehouse-near-miss*, press Play.
Tracks and trails move; switch to Settings and run the live Muse Spark test,
then show `docs/LIVE_META_VERIFICATION.md`: SAM 3.1's real boxes and
confidences (0.94, 0.97) from an actual API response, parsed live.

**35–55s — Reveal.** Click **Run analysis**. The near-miss event appears; click
it — the player seeks to the event time. Open the Inspector: calibration,
units, occlusion windows, assumption register. "Every number has a source."

**55–75s — Counterfact.** In the Counterfactual screen ask: *what if the
forklift had slowed earlier?* Drag speed reduction to 40%, intervention to
1.0s. The chart and Δd_min update from a fresh server simulation; Monte-Carlo
p05/p50/p95 shown with the seed. Show the Agent Trace: Muse Spark's
hypothesis stage (or fixture replay, honestly labelled), simulation,
independent verification — PASS.

**75–90s — Prove & export.** Tick human approval, open Evidence, download the
hash-bound JSON. "FrontierSight: models propose, geometry decides, humans
approve — and anyone can replay the proof. No safety certification claimed;
every limitation is on the label."
