# Web release — 2026-10-28

- Mobile navigation uses one native modal drawer; profile and theme controls remain in the header.
- SAM Vision has three locally hosted, attributed Unsplash physical-AI photographs and user uploads.
  Actual binary masks drive 2D cutouts and textured, explicitly assumed 3D extrusions.
- Scene views now include warehouse, street and robotics scenery. Decorative objects do not enter collision analysis.
- Create Lab is a compact desktop workbench: independent preview/inspector scrolling,
  components first, one component's fields expanded, collapsible generators/floor settings.
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
