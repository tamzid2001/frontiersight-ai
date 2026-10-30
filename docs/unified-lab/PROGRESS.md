# Unified editor implementation progress

The 0.39 foundation merged as 6b050e5 and its production health returned 0.39.0.
The current feature branch is feat/unified-create-lab-20261030. This is an active
engineering milestone, not a declaration that the full product acceptance is done.

Implemented: single Create Lab navigation; transactional canonical document store;
monotonic revisions, bounded history and recoverable undo/redo checkpoints; 3D
selection/move/rotate/scale via licensed Three r160 TransformControls; independent
viewport/timeline zoom; shared playhead; timestamped object tracks; worker controls
under Results; complete-scene counterfactuals supporting structural changes; app-owned
Firestore editor project persistence with history/schema/security validation.

The default 3D, top view, video split and counterfactual use the same document.
Original planar input tools remain explicitly archived migration inputs; a conversion
is labeled assumption-based and retains original source semantics. Their full curved
paths are not claimed to be measured 3D paths.

Executed: 320 Python tests passed before the additional complete-scene comparison
case; 35 Node helper tests passed (99.44% lines /94.99% branches). Additional targeted
HTTP/MCP/schema/history tests and actual browser duplicate/undo/redo/view switching
ran. The headless Chromium regression workflow is newly authored; its result is
pending GitHub execution. No camera, live SAM, ROS, robot or GPU validation is claimed.

Next: secure URDF importer/kinematics, articulated crane attachment/release and support
verification; shared REST/MCP model and plan operations; telemetry forecast adapter and
chronological baseline evaluation. SDF/native dynamics, mesh resolution and real hardware
must remain capability-gated until separately implemented and verified.
