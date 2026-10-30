# Local video and shadow runtime

Python 3.12+ for optional PyAV 19/OpenCV 4.14 wheels. Linux x86-64 deployment is
the primary camera target. Actual local validation ran on macOS ARM64, including
MP4 decoding and replay. USB/RTSP cameras, Jetson, ROS 2 and Docker execution
require their own integration verification; none is implied by CPU tests.

```sh
python -m pip install -e '.[dev,edge]'
python -m edge.server --origin http://127.0.0.1:8000
# Token: ~/.local/share/frontiersight-edge/operator-token (0600)
# In Video Studio expand “Video upload jobs & local shadow intelligence”.
# Connect http://127.0.0.1:8830 using that local operator token.
```

No API key/token appears in a URL. The token is never stored in browser storage
and clears on Clerk workspace switch. The server binds loopback, verifies bearer
auth and explicit origins, has no arbitrary remote URL ingest and exposes no
actuator operation. This is a **single local operator workspace**, not shared
multi-tenant cloud storage. Use independent OS accounts/roots to separate operators.
HTTPS/VPN and an independently reviewed authenticated reverse proxy are required
before deliberate remote exposure. Never simply bind this worker to the Internet.

Uploads accept 1 MiB chunks with a confirmed byte offset. Pausing/resuming upload
queries the server offset. A crash-tail is truncated to the durable ledger offset.
Quota defaults: 64 MiB/file, 512 MiB aggregate reservations, 20 jobs, 24h retention.
PyAV probes actual container/codec and decodes actual PTS. MP4/MOV/WebM; H.264,
HEVC, VP8/VP9, AV1, MPEG4; ≤3840×2160; ≤120s/3600 frames. Only one video stream.
Uploaded files cannot fetch playlist/network protocols. Decoder work runs in a
killable process. Large content/codec inspection is never a Vercel request.

Inspection mode makes no model call. SAM mode requires your local `MODEL_API_KEY`
and explicit UI consent to transmit the video to Meta. It is limited to 512 source
frames and 1–4 noun phrases, each a separate model request with separate identities.
Files API uploads use `purpose=user_data`. An owned provider copy is deleted on
normal completion/failure when its ID is known; a killed/uncertain upload can leave
a provider copy. Local deletion cannot promise provider deletion/retention.

The ledger survives browser refresh and worker restarts. Reopen by job ID. Pause
is supported before provider work starts. Already-sent model calls cannot be
safely paused/replayed. Interrupted requests become `failed_or_unknown`; they
never auto-retry. Inspect metadata/results before creating any deliberate new
request. Background work is serialized; supervisor shutdown terminates its own
child. Retention cleanup does not delete an active job.

## Actual offline replay

```sh
PYTHONPATH=. python scripts/make_video_replay.py /tmp/replay.mp4
python -m edge.runtime --source file --input /tmp/replay.mp4 \
  --output ~/.local/share/frontiersight-edge/live-state.json --max-frames 4
```

The generated MP4 contains genuinely variable PTS and has an authored fixture
sidecar with a content hash. Its boxes are **FIXTURE**, not SAM output. The replay
runtime really decodes frames. Without `--sam`, it publishes metadata and no
tracks, then explicitly marks end-of-file disconnected/stale. File pacing uses
`--fps`; source PTS is preserved, not claimed to equal wall-clock playback.

```sh
# Operator explicitly starts a local camera; connecting the website does not.
python -m edge.runtime --source usb --input 0 --sam --concept person \
  --output ~/.local/share/frontiersight-edge/live-state.json
python -m edge.runtime --source rtsp --input rtsp://camera.example/stream \
  --allow-rtsp-host camera.example --sam --concept forklift \
  --output ~/.local/share/frontiersight-edge/live-state.json
```

Keep authenticated RTSP URLs outside command arguments. Prefer a local gateway
without credentials in its URL. RTSP/USB acquisition reports disconnects and attempts three reconnects to the
same explicitly configured source (1/2/4s backoff). After the retry budget,
restart after diagnosis. Reconnect policy has software-fixture tests; camera
reconnection on physical equipment remains unverified.
PyAV file and OpenCV camera acquisition run in a separate process; both FFmpeg
runtimes are not imported into the same acquisition process on macOS.

Acquisition queue depth=2, latest-frame drop policy, bounded track history=20,
32 detection candidates, sampled remote inference (default ≥2s between starts).
Source monotonic capture time is distinguished from actual sensor timestamps,
which ordinary OpenCV camera reads do not guarantee. Independent SAM image calls
use provisional nearest-centre association, which can switch identities. No ego-
motion compensation, multi-camera fusion or certified tracking accuracy is claimed.

Live Intelligence polls authenticated `/state` while its panel is visible. It
shows actual freshness, connection, source, calibration and latency fields.
Predictions are invalidated beyond 2s observation age. Slow remote inference
therefore becomes visibly stale; it is not a camera-rate guarantee. No inference
latency is reported when no inference occurred. Host capture-to-consumer latency
is distinct from camera exposure latency. The deterministic simulator remains
independent of model availability.

## ROS 2 Jazzy, observation only

On Ubuntu 24.04 with a properly sourced ROS 2 Jazzy installation and
`geometry_msgs`, `std_msgs`, `diagnostic_msgs`:

```sh
python -m integrations.ros2_shadow --state-file ~/.local/share/frontiersight-edge/live-state.json
```

Publishes `frontiersight/world_poses` (`geometry_msgs/PoseArray`),
`world_state_v2`/`risks_v2` (`std_msgs/String`, versioned JSON) and
`diagnostics` (`DiagnosticArray`). Pose/state/risk QoS: best-effort, volatile,
keep-last depth1; diagnostics depth10. Header stamps are publication time;
source timestamp kind/PTS and pose provenance remain explicit in JSON.
Stale snapshots publish empty poses/risks plus warnings. Assumption-based poses
retain that status in state/diagnostics; they are not measured robot transforms.
No TF authority is established automatically and no actuator topic is published.

The local authenticated `/mcp` exposes `inspect_live_session` and
`get_tracking_diagnostics`. The public cloud MCP has no implicit access to your
camera or local worker token. ROS publisher execution remains NOT RUN unless the
supported ROS environment is actually available.

## Container and service

```sh
docker compose -f compose.edge.yml up --build
```

The container binds internally on 0.0.0.0 only with explicit container configuration;
Compose publishes **127.0.0.1:8830**, drops capabilities and uses a non-root user,
read-only root and a persistent data volume. It does not mount camera devices.
For a Linux service use a dedicated unprivileged OS account, private data directory,
`ExecStart=/path/to/venv/bin/python -m edge.server --root /var/lib/frontiersight-edge`,
`Restart=on-failure`, `NoNewPrivileges=true`, `ProtectSystem=strict` and an explicit
`ReadWritePaths=/var/lib/frontiersight-edge`. Do not put keys in a unit file or Git.

OFFLINE_REPLAY and SHADOW are supported execution modes. Advisory envelope
validation is a pure function in `edge/safety.py`, always `actuation=false`.
CONTROLLED_BENCH/physical actuation and manufacturer drivers are not implemented.
Independent E-stops, safety PLCs, interlocks and site commissioning remain required
for any separate physical control system. Software simulation is not certification.
