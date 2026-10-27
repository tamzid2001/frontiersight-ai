# Deep review of the Create Lab prompt — and the expert prompt it became

## The original prompt (owner, verbatim intent)
> "Instead of Upload Lab it should be Create a Lab, where users can create
> components, set paths and make the objects move on a set path and then run
> analysis."

## Deep review — what was strong, what was underspecified
**Strong:** a clear product pivot (creation over ingestion), a clear verb chain
(create → set path → animate → analyse), and an implied promise that the
existing analysis pipeline is reused rather than rebuilt.

**Underspecified — each item below would have produced a different product in
different hands:**
1. **Component model.** What *is* a component? Category taxonomy, physical
   radius, static vs moving, default speeds — none defined. Without a radius
   there is no collision geometry; without categories there is no colour/label
   language shared with the rest of the product.
2. **Path model.** Waypoints or curves? Constant speed or speed profile? Start
   delay? What happens at the end of a path — stop, loop, disappear? Each
   choice changes the sampled tracks and therefore every downstream number.
3. **Interaction model.** Click-to-add? Drag to move? How are mistakes undone?
   What is selected, and how does the user know? An editor lives or dies here.
4. **Units and stage semantics.** Pixels or metres? If undefined, the analysis
   layer must (correctly, per our calibration rule) refuse metric claims —
   silently downgrading the user's creation to pixel space.
5. **Validation.** What stops a user running analysis on one object, a pathless
   object, or a zero-speed mover? Editors need guardrails with plain-language
   reasons, not stack traces.
6. **Analysis handoff.** Which object is the counterfactual agent? What does
   the user see first after running — the verdict, the trace, or the chart?
7. **Empty state.** A blank canvas with no template teaches nothing. The first
   10 seconds decide whether the feature is understood.
8. **Persistence/sharing.** Can a scene be saved, exported, re-imported,
   shared as a link? Researchers need reproducibility, not one-off play.

## The expert-oriented prompt (use this to brief any designer/engineer/AI)
> **Design and build "Create Lab", a scene-authoring surface inside
> FrontierSight AI, replacing Upload Lab.**
>
> **User goal (one sentence):** a robotics or safety researcher composes a
> physical scene from components, assigns each a path and speed, previews the
> motion, and runs the identical deterministic analysis used for built-in
> scenarios — without writing code.
>
> **Component model:** palette of Forklift, Pedestrian, Robot, Vehicle,
> Cyclist, and static Shelf. Every component has: unique id (category + counter),
> category colour shared with the Studio, radius in metres (collision geometry),
> speed in m/s (0 only for static), start delay in seconds. Sensible defaults
> per category; every field editable inline.
>
> **Stage semantics:** a 16 × 14 m floor plan rendered as a canvas grid at
> metre resolution (0.1 m snapping). Because the stage is metres by
> construction, metric claims are valid without a separate calibration step —
> say so in the UI.
>
> **Path model:** ordered waypoints (polyline), constant speed along the path,
> optional start delay, stop-and-hold at the final waypoint. Sampling: 10 Hz
> into timestamped tracks. Duration is derived (max over components, capped),
> never typed in by the user.
>
> **Interactions:** (1) Add component → it becomes selected. (2) Click stage →
> append waypoint to the selected component. (3) Drag any waypoint of the
> selected component to move it. (4) Undo point / Clear path / Delete per
> component card. (5) Play/Pause preview plus a scrubber; each component's
> live marker shows its name, speed, and footprint circle (radius). Selected
> state is visible on both canvas and card. All actions work without a mouse
> where feasible; every failure message states the cause and the fix.
>
> **Guardrails (validate before sampling, in this order):** at least two
> components; every component has ≥1 waypoint; a multi-point path with speed 0
> is an error naming the component. Errors appear next to the Run button, not
> in a console.
>
> **Templates over blank canvas:** preload a near-miss template on first open;
> offer Near-miss / Crossing / Robot-cell templates that *replace* the scene
> and announce themselves ("Template X loaded — edit any path").
>
> **Analysis handoff:** Run analysis samples tracks, POSTs them to the existing
> custom-scene pipeline (all-pairs CPA/TTC → Spark hypothesis → braking
> counterfactual → independent verification → human-gated export), and lands
> the user in the Studio at t=0 with the events list populated and the agent
> trace one tab away. The created scene must also work in the Counterfactual
> screen (agent defaults to the first moving component).
>
> **Persistence:** Export downloads the scene definition JSON
> (stage size + components + waypoints); Import restores it exactly. Analysed
> scenes are kept in browser local storage (last 10), never silently uploaded.
>
> **Honesty rules (non-negotiable, inherit from the product):** sampled tracks
> are labelled USER_CREATED; the preview is a visualisation of declared paths,
> not a physics simulation; analysis numbers come only from the deterministic
> engine; if the Meta API is unconfigured, stages say FIXTURE_REPLAY /
> BLOCKED_CREDENTIALS rather than implying live model work.
>
> **Acceptance criteria:** (a) a first-time user can go from load to an
> analysed near-miss in under 60 seconds using only the template + Run;
> (b) dragging a waypoint and re-running measurably changes d_min in the
> expected direction; (c) exporting and re-importing a scene reproduces the
> identical analysis manifest; (d) invalid scenes produce named, actionable
> errors; (e) the flow works at 390 px width with the component list below the
> stage.
>
> **Anti-goals:** no freehand drawing, no spline editor, no per-segment speed
> profiles, no 3D — until the waypoint model is proven in user testing.

## What was implemented against this prompt
Create Lab exactly as specced above (canvas editor with add/drag/undo,
per-component speed/radius/delay, 3 templates with near-miss preloaded,
10 Hz sampling, guardrail errors naming the component, export/import JSON,
local-storage history, handoff into Studio + Counterfactual). Deliberate
v1 exclusions, matching the anti-goals: polylines only (no splines), constant
speed per component (no per-segment profiles), stop-and-hold at path end
(no looping). These are the first candidates for a v2 once the waypoint
model is exercised.
