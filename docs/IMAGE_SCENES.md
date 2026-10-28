# Image scenes and physical-AI scenery

In **Video Studio → SAM Vision**, select a photograph using Previous/Next or
upload a JPEG, PNG or WebP (up to 12 MB). Choose one short noun phrase per concept,
then press Segment. The browser sends a resized JPEG only after this action.
The server accepts bounded JPEG/PNG data URLs and calls Meta SAM 3.1.
A second concept uses a separate request; IDs are scoped by concept and response.

Press **Build image-based 2D / 3D scene** after detections arrive. The 2D view
uses the actual photograph and binary alpha masks decoded by Meta's official
`meta-sam-parser==0.1.0`. It never fabricates a mask. Undecodable masks are explicitly
shown as bounding-box regions. Hide the photograph to inspect isolated cutouts,
and toggle individual objects. JSON export includes source pixels, decoded mask
PNGs, image-space bounds, provenance, assumed depth and example-photo attribution.

The 3D view uses photo-textured cutout faces and a bounded instanced silhouette
extrusion. Thickness and image-relative layering are assumptions. No hidden
surface, metric depth, mass, material, motion or collision validity is recovered
from one photograph. This view is separate from Create Lab's calibrated planar
physics. On devices without WebGL, 2D cutouts and JSON export remain available.

## Scenery and navigation

Create Lab supports warehouse, street and robotics-workcell scenery, selected
from actor categories by default. The same context appears in Studio and
Counterfactual views. The 3D context includes racks, cartons, workcells, trees,
buildings, lane markings and walls as appropriate. Solid decorative props sit
outside the analysis stage. They are not collision objects; add a modeled
component when an obstacle must participate in analysis. Each 3D view owns its
coordinate extent and releases resources when rebuilt.

At widths up to 900 px, the primary navigation becomes a native modal side drawer.
Escape, dismissal and navigation close it; native dialog semantics contain focus
and return it to the menu button. Header theme and sign-in controls remain
accessible. Desktop and mobile use one navigation tree, preserving handlers.

## Resource limits and validation

- Input frame: longest edge 1,440 px, JPEG data URL at most 3.5 million characters.
- Decoder: at most 1 million pixels per mask, 4 million per response; 48 records
  per frame and 512 frames. Budget/decoding failures are explicit diagnostics.
- Scene: at most 24 objects, 32×32 voxel sampling per object; render on demand.
- Provider errors, incomplete streams and timeouts are errors, not zero matches.
- Image source changes cancel stale work and revoke temporary browser URLs.

Run `python -m pytest -q` and `node --test tests/web-scenes.test.mjs`.
CI also emits LCOV for image-space/scenery control code. This coverage does not
measure GPU execution or model accuracy. Browser checks separately verify actual
WebGL rendering, navigation, upload, object toggles and gallery attribution.

On 2026-10-28, a live Meta SAM request for the warehouse example detected one
forklift (confidence 0.871), decoded its silhouette and rendered the actual cutout
in both views. This is one functional integration check, not an accuracy benchmark.

## References and licensing

- [Meta SAM output grammar](https://dev.meta.ai/docs/sam/reading-segmentation)
- [Meta client libraries](https://dev.meta.ai/docs/sam/client-libraries)
- [Three.js InstancedMesh lifecycle](https://threejs.org/docs/pages/InstancedMesh.html)
- [Unsplash License](https://unsplash.com/license)

`apps/web/sam-gallery.json` records each photographer, source, license and SHA-256.
Photographs remain under the Unsplash License, not this repository's MIT license.
Meta's decoder is an installed dependency under its upstream SAM license; it is
not copied into this repository. Vendored Three.js retains its MIT notices.
