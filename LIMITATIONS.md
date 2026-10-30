# Verified boundaries

- Original 2D scene/path workflows remain. The new v2 engine represents genuine
  XYZ/quaternion states and a constrained prismatic hierarchy. It is kinematic
  prediction, **not a complete rigid-body/contact, articulated-arm or vehicle
  dynamics simulator**. It does not model tipping, deformation, pallet release,
  aerodynamics, torque-driven joints or physically certified manufacturing.
- Forklift scenarios use synthetic geometry, declared actuator limits and an
  explicit rigid payload attachment. The flying vehicle is hypothetical. Neither
  establishes manufacturer compatibility or real-world safety.
- Exact supported geometric contacts and conservative possible contacts are
  labeled separately. OBB/capsule bounds and sampled clearance minima must not be
  presented as exact all-time Euclidean clearance. Consult the numerical reference.
- Monocular SAM segmentation cannot produce metric depth. Plane, scale and height
  conversions are assumptions. Submitted sensor/calibration evidence is caller
  declared, not independently authenticated metrology. Camera motion and uncertain
  identities remain explicit. Statistical confidence/quantiles are not fabricated.
- Local MP4 variable-timestamp decoding/replay and durable job behavior were
  executed. New live SAM video/language-physics workflows use provider fixtures in
  tests; live access and industrial-video accuracy remain unverified. Historical
  model verification in older documents does not validate these new workflows.
- USB/RTSP input and ROS 2 Jazzy publishing have executable adapters but no physical
  camera/ROS environment was used. The bounded reconnect policy is software-tested; physical camera reconnect,
  multi-camera/depth fusion, persistent cross-occlusion identity and Jetson deployment
  remain unverified or unimplemented. Ordinary OpenCV reads do not supply a certified sensor clock.
- Camera acquisition, remote inference and deterministic prediction have separate
  rates. Stale/disconnected state invalidates predictions. No camera-rate,
  hard-real-time or automotive safety guarantee is made.
- Video jobs live in a separately running local worker. Vercel has no durable
  large-video queue/object store provisioned. Local quota/24h retention do not
  establish deletion of copies at a model provider, especially interrupted uploads.
- FrontierSight's own Clerk app is retained. Production DNS is pending. Firestore
  app namespaces/profiles are implemented/tested with the real emulator; a restricted
  production runtime credential is still required. No broad personal GCP credential
  is copied into Vercel. Checkout remains blocked until durable storage and production
  auth are valid, even though the Stripe catalog/webhook exist.
- Shared Firestore app namespaces are application isolation, **not separate
  physical databases or collection-scoped IAM isolation**. Server authorization and
  appropriately scoped runtime identities remain necessary.
- No robot actuation, road-vehicle control, manufacturer command driver or certified
  emergency-stop function is implemented. Shadow observations and pure advisory
  validation do not replace a safety PLC, interlock, physical E-stop or site approval.
- Optional GPU, physical robot, camera, ROS and real industrial model evaluations
  are **NOT RUN**. CPU/Cobertura coverage does not measure those capabilities.
