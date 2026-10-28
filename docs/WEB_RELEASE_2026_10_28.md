# Web release — 2026-10-28

- Mobile navigation uses one native modal drawer; profile and theme controls remain in the header.
- SAM Vision has three locally hosted, attributed Unsplash physical-AI photographs and user uploads.
  Actual binary masks drive 2D cutouts and textured, explicitly assumed 3D extrusions.
- Scene views now include warehouse, street and robotics scenery. Decorative objects do not enter collision analysis.
- Create Lab is a compact desktop workbench: independent preview/inspector scrolling,
  AI generators first, one component's fields expanded, collapsible floor settings.
  At smaller widths it becomes one ordinary scrolling column.
- Homepage feature buttons retain visible labels in both themes. Generator buttons open the relevant tool.
- The sign-in page uses Clerk exclusively. Duplicate password/signup forms and the SQLite deployment notice
  were removed from the UI. Legacy API compatibility remains; this UI change is not a database migration.
- Hidden canvas work is deferred; hidden 3D views stop rendering. Image gallery assets load only on opening Studio.

Validation includes Python tests with the actual Firestore emulator, ten Node image/scenery control tests,
LCOV generation, browser phone/drawer checks, actual WebGL rendering, and live SAM calls on a licensed example
and the uploaded-image path. A forklift was detected at confidence 0.871 and its decoded mask rendered.
One integration sample does not establish segmentation accuracy on an industrial dataset.

The 18 private enterprise website upgrades are published on isolated feature branches. Production activation
of their Firestore and paid API/MCP paths remains gated on server identity, published rules verification,
Clerk configuration and verified billing/promotion setup. No new cloud resources or IAM changes were made.


## Scene editing and compact analysis workbenches — v0.37.0

- Floor resizing scales and fits all paths, including the engine's sampled smooth-curve
  envelopes. Object radius, speed, delay and identity remain unchanged. Dimensions
  persist with workspace, share-link and JSON round trips.
- Move complete paths by dragging object bodies in 2D or 3D, clicking a destination,
  editing Start X/Y or using focused-canvas arrow keys. A separate Edit paths mode
  retains waypoint insertion, dragging and deletion. Canceled drags restore the path.
- Video Studio uses a viewport-sized preview, compact playback and a bounded inspector.
  SAM Vision and extended inspection remain available in expandable sections.
- Counterfactual now has compact scene/preset controls, matching 2D/3D preview heights,
  a bounded desktop intervention/results panel, and expandable legend/separation chart.
  At 1280 × 768 its initial comparison workbench ends at y=756, inside the viewport.
  At 390 × 844 both workbenches use normal vertical scrolling without horizontal overflow.
- HTTP scene resize/reposition and both corresponding MCP tools use the same Python
  engine and published OpenAPI request definitions. HTTP and local stdio are tested.
  Editing is pure and does not write saved scenes or spend model credits.

See [Scene editing API](SCENE_EDITING_API.md) and [coverage evidence](SCENE_EDITING_COVERAGE.md).


### Complete scene context and pricing/authentication

- Canonical scene preparation preserves floor, component definitions, appearance,
  radii, speeds, delays, modes and sampled tracks. Studio and Counterfactual adopt
  newer Lab revisions and invalidate stale runs; 3D rebuilds on changed source data.
  Counterfactual uses the declared floor and the actual sampled duration.
- The same complete scene is supported by HTTP analysis/simulation and MCP sampling/
  simulation. Target filtering works on custom scenes. The published OpenAPI covers
  the complete-scene contract as well as backward-compatible tracks requests.
- Pricing now presents product benefits and clear monthly/yearly offers; the annual
  CTA correctly shows $190/year. Clerk is the sole sign-in UI, with branded styling.
  Clerk Billing no longer replaces the actual Stripe plan cards without a configured
  subscription contract. Privacy copy describes actual account/model/storage flows.
- Checkout verifies Stripe price amount, currency, interval and live mode before
  creating a session. Availability is server-declared; unavailable checkout does not
  silently enroll a customer in a waitlist or pretend payment was completed.
- **Production activation remains incomplete:** Clerk has no production instance,
  Stripe variables are absent and the native account/subscription store is SQLite.
  Live checkout is blocked on Vercel's temporary storage. A tested durable store,
  production Clerk domain/DNS/OAuth, encrypted billing configuration and end-to-end
  live verification are still required. No provider activation or payment occurred.

### Startup work

Create Lab's starter and hidden canvas allocation are deferred until first use.
The mobile navigation initializes before the application scripts; all three
scripts use ordered `defer`. Guest workspace discovery no longer initializes
Clerk on Overview, and hidden Counterfactual simulation is not run on page load.
The existing Lighthouse budgets are unchanged.

Below-fold feature grids and the architecture block now defer rendering with
intrinsic size estimates, only on viewports up to 900 px high where they were
confirmed below the initial fold. Sequential keyboard navigation across both
boundaries was verified. Mobile navigation initializes before main content is
parsed, and mobile headers use an opaque background instead of a backdrop blur.
Lighthouse is pinned to the actually inspected 13.6.0 release and reports runner
benchmark index/TBT; its score thresholds and throttling remain unchanged.

The healthy sign-in hint and outer card have been removed at the user's request;
Clerk's own form remains. Error/retry feedback is retained when authentication
cannot load.
