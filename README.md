# ROS2 Person-Presence Demo — Jetson Orin Nano (CSI IMX219)

Four-container ROS 2 Jazzy pipeline for JetPack 7.2 (L4T r39.2, Ubuntu 24.04
noble), deployed to balenaCloud. The two Jetson-specific services are stages of
one multi-stage `Dockerfile` selected per service with `build.target`; the other
two use the upstream `ros:jazzy-ros-base` image.

```
camera (gscam, CSI)  →  detection (YOLO26s, TensorRT)  →  logic (presence events)
        └──────────────────────── viz (foxglove_bridge :8765) ────────────────────┘
```

| Service   | Image                                   | `runtime: nvidia` | Publishes                                                   |
|-----------|-----------------------------------------|-------------------|-------------------------------------------------------------|
| camera    | `Dockerfile` stage `camera`             | yes               | `/image_raw`, `/camera/image_raw/compressed`                 |
| detection | `Dockerfile` stage `detection`          | yes               | `/detectnet/detections`, `/detectnet/overlay[/compressed]`   |
| logic     | `ros:jazzy-ros-base`                    | no                | `/presence/events`, `/presence/count`                        |
| viz       | `ros:jazzy-ros-base`                    | no                | Foxglove websocket on `:8765`                                |

## Prerequisites on the Jetson

- JetPack 7.2 (L4T r39.2.x) host. The CUDA 13.2 userspace in the detection
  container needs the matching R595+ host driver.
- IMX219 CSI camera connected and enumerated by the right dtbo.
- Proof-of-concept balenaOS with a supervisor and host extensions that provide:
  - `nvargus-daemon` running on the host
  - NVIDIA container runtime configured for balena-engine

## Images

NVIDIA stopped publishing `nvcr.io/nvidia/l4t-jetpack` after r36.4.0 (JetPack 6).
The root `Dockerfile` installs the Jetson pieces from the L4T r39.2 apt repo
(`repo.download.nvidia.com/jetson/common`), following
[NVIDIA's public recipe](https://gitlab.com/nvidia/container-images/l4t-jetpack).

| Stage       | Adds on top of the previous                                              | Compressed |
|-------------|---------------------------------------------------------------------------|------------|
| `base`      | noble, ROS Jazzy `ros-base`, CycloneDDS, L4T + ROS apt repos. No CUDA.     | —          |
| `camera`    | GStreamer plugins, unpacked `nvidia-l4t-gstreamer` (`nvarguscamerasrc`, `nvvidconv`), gscam. No CUDA. | ~0.5 GB |
| `detection` | `cuda-cudart-13-2`, `libcurand-13-2`, TensorRT 10.16 runtime + Python bindings, OpenCV, pycuda (built from source). | ~2.9 GB |

`libnvinfer10` alone is 2.9 GB uncompressed and unavoidable. Everything else was
trimmed after a first cut with the full CUDA library set weighed 11.7 GB per
image. Compose points `camera` and `detection` at the same `Dockerfile` with
different `build.target` values; `logic` and `viz` keep their own Dockerfiles.

Build a single stage locally:

```bash
docker build --target camera -t ros2-demo/camera:dev .
```

## Deploy

Stock balena CLI rejects two things this compose file needs: `runtime: nvidia`
and the `/tmp/argus_socket` bind mount. A patched CLI lives on the
[`allow-runtime-and-bind-mounts` branch](https://github.com/balena-io/balena-cli/pull/3122)
and CI publishes it as an update channel:

```bash
balena update allow-runtime-and-bind-mounts   # install the branch build
balena update stable                          # go back afterwards
```

`build.target` is supported by balena but
[incompatible with Livepush](https://docs.balena.io/reference/supervisor/docker-compose/),
so local-mode `balena push <ip>` does full rebuilds instead of live sync.

Deploy with:

```bash
balena deploy <fleet> --build --nologupload
```

`--nologupload` is required for now. The CLI caps each service's build log at
512 KB *before* JSON encoding, the API caps request bodies at 512 KB *after*,
so any service whose build log hits the cap (detection does, via pycuda's
compiler output) fails the release with `Payload Too Large`.

Expect the first upload of the two Jetson images to take an hour or more on a
home uplink. Registry blob commits for gigabyte layers can exceed Docker's
response-header timeout; the CLI retries, and re-running the same deploy skips
every layer that already landed.

The detection image bakes in `yolo26s.onnx` (exported once from `yolo26s.pt`
with ultralytics, see the comment in the `Dockerfile`). The **first** detection
start takes several minutes while TensorRT builds the FP16 engine; the engine
is cached in the `trt-cache` named volume under a filename that includes the
TensorRT version, so a JetPack upgrade triggers a rebuild instead of a
deserialization failure.

## Connecting Foxglove

### Local network
In [Foxglove Studio](https://foxglove.dev/download) on your laptop or via the web interface setup:
*Open connection → Foxglove WebSocket →* `ws://<jetson-ip>:8765`.

### Remote access (cloud relay)
foxglove_bridge ships a `remote_access` gateway that connects outbound to
Foxglove's platform — no inbound port, no VPN required. To enable, set these
two env vars on the device (balena device or fleet variables):

| Variable                | Value                                                                 |
|-------------------------|-----------------------------------------------------------------------|
| `FOXGLOVE_REMOTE_ACCESS`| `true`                                                                |
| `FOXGLOVE_DEVICE_TOKEN` | Token from [foxglove.dev → Devices → Create Device Token](https://app.foxglove.dev/) |

Restart the `viz` service; the device then shows up under your Foxglove org's
Devices list and can be opened from any browser.

Useful panels: Image (`/image_raw` or `/detectnet/overlay`), Raw Messages
(`/detectnet/detections`, `/presence/events`), Plot (`/presence/count`).
System stats (CPU/RAM) stream on `/foxglove_bridge/sysinfo`.

## Gotchas

- **Argus socket**: `nvarguscamerasrc` inside the container talks to the host's
  `nvargus-daemon` through `/tmp/argus_socket` (bind-mounted in compose). If the
  camera container logs `Failed to create CaptureSession`, check the daemon is
  running on the host and restart it: `sudo systemctl restart nvargus-daemon`.
- **Argus libs come from the host**: the `camera` stage only unpacks the
  `nvarguscamerasrc`/`nvvidconv` plugins. `libargus`, `libnvbufsurface` and the
  rest are bind-mounted by the NVIDIA container runtime from the host's
  JetPack 7.2 install. The `lsmod: not found` lines and the `nvsipl` /
  `nvdeinterlace` plugin-load warnings at camera start are harmless.
- **TRT first run**: engine build takes minutes and looks like a hang — watch.
  `foxglove_bridge` logs `Failed to retrieve parameters from node '/detectnet'`
  during the build because the node is not spinning yet; it recovers.
  Deleting the `trt-cache` volume forces a rebuild.
- **Never purge `python3-dev` in a ROS image**: `ros-jazzy-fastrtps` depends on
  it, so `apt-get purge --auto-remove python3-dev` removes the entire ROS tree
  and `-y` accepts silently. The detection stage asserts `/opt/ros/jazzy` still
  exists after its cleanup step.
- **pycuda is built from source** in the detection image. Its configure step
  finds CUDA only via `nvcc` on PATH, so `cuda-nvcc-13-2` plus the CUDA dev
  headers (`cudaProfiler.h` lives in `cuda-profiler-api-13-2`) are installed
  for the build and purged in the same layer. If the build breaks on a future
  pycuda release, `cuda-python` is NVIDIA's own binding and the fallback.
- **CycloneDDS / RMW**: every service sets `RMW_IMPLEMENTATION=rmw_cyclonedds_cpp`
  and `ROS_DOMAIN_ID=42`. FastDDS shared-memory transport
  breaks across container boundaries, and nodes on different RMWs fail discovery
  *silently* — if a topic list looks empty, check these two env vars first.
- **No host networking**: containers discover each other via multicast on the
  `rosnet` bridge. Topics are not visible from the Jetson host itself; use
  `docker compose exec <service> bash` to introspect.
- **Root `.dockerignore` applies to the whole project** under balena CLI. Do not
  list service directories in it; they would be stripped from the upload.
