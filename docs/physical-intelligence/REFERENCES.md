# References actually inspected — 2026-10-30

Original implementation; no upstream source or assets copied into the engine.
API compatibility is constrained to the following inspected contracts.

| Primary source | Applied decision |
|---|---|
| [Meta SAM output grammar](https://dev.meta.ai/docs/sam/reading-segmentation) | Stream must end on `response.completed`; identity is scoped to one response; boxes/confidence/mask headers are retained; zero matches is valid. |
| [Meta official video example](https://github.com/meta-models/meta-model-cookbook/blob/main/07_sam/01_api_basics/python/02_upload_and_segment_video.py) and [shared API helper](https://github.com/meta-models/meta-model-cookbook/blob/main/07_sam/01_api_basics/python/sam_api.py) | Files API `purpose=user_data`, `input_video` file ID and separate concept requests; parsed output must be complete. Inspected implementation, not vendored. |
| [PyAV timing](https://pyav.org/docs/stable/api/time.html) and [containers](https://pyav.org/docs/stable/api/container.html) | Use decoded frame PTS × time_base, not a guessed constant FPS. Actual installed/tested PyAV 19.0.2 APIs verified by MP4 encode/decode/replay. The stable docs resolve to an older documentation build, so installed API execution is the compatibility evidence. |
| [OpenCV Video I/O](https://docs.opencv.org/4.x/d4/d15/group__videoio__flags__base.html) | Explicit camera/RTSP adapters, timeout options where supported, read failure and release handling. Installed OpenCV 4.14.0.94 imports; camera hardware not exercised. |
| [ROS 2 Jazzy QoS source](https://github.com/ros2/rclpy/blob/jazzy/rclpy/rclpy/qos.py), [PoseStamped definition](https://github.com/ros2/common_interfaces/blob/jazzy/geometry_msgs/msg/PoseStamped.msg) | Best-effort volatile bounded state topics; publication and observation timestamps kept distinct. Official hosted Jazzy QoS web documentation returned access denied; source used instead. Actual ROS publisher is NOT RUN. |
| [Clerk CLI](https://clerk.com/docs/guides/development/clerk-cli) | Official CLI 4.1.0 doctor verified the FrontierSight application/instances and pending DNS. User selected FrontierSight's own application, not the supplied Quantura application. |

Dependency isolation: PyAV/OpenCV are optional `edge` extras for Python 3.12+.
The Vercel API does not install/import native camera dependencies. ROS comes from
its supported host installation, not an invented pip package. Original source
remains MIT. Dependencies and bundled codecs retain their respective licenses;
PyAV/FFmpeg wheel codec license/build options require review before redistributing
a particular binary/container. No NVIDIA/CUDA, hardware or GPU acceleration claim
is made for this CPU release.
