# ROS2 Person-Presence Demo — Jetson Orin Nano (CSI IMX219)

Four-container ROS 2 Humble pipeline on plain docker-compose, all built on
NVIDIA's official `nvcr.io/nvidia/l4t-jetpack:r36.4.0` base (Ubuntu 22.04
jammy). Architecture is unchanged from the original Jazzy plan — we'll migrate
to Jazzy when JetPack 7.2 lands on Orin (Ubuntu 24.04 noble).

```
camera (gscam2, CSI)  →  detection (detectnet, TensorRT)  →  logic (presence events)
        └──────────────────────── viz (foxglove_bridge :8765) ────────────────────┘
```

| Service   | Base image                                | GPU | Publishes                                  |
|-----------|-------------------------------------------|-----|--------------------------------------------|
| camera    | `nvcr.io/nvidia/l4t-jetpack:r36.4.0`      | yes | `/image_raw`                                |
| detection | same                                      | yes | `/detectnet/detections`, `/detectnet/overlay` |
| logic     | same                                      | no  | `/presence/events`, `/presence/count`       |
| viz       | same                                      | no  | Foxglove websocket on `:8765`               |

## Prerequisites on the Jetson

- JetPack 6.x (L4T r36.4.x), IMX219 CSI camera connected and enumerated
- `nvargus-daemon` running on the host (default on stock JetPack): `systemctl status nvargus-daemon`
- NVIDIA container runtime configured for Docker (`docker info | grep nvidia`)
- docker compose v2

## Bring-up order

Bring the camera up **alone** first — it validates the argus socket mount before
anything else is built:

```bash
docker compose up --build camera
# in another shell:
docker compose exec camera bash -c "ros2 topic hz /image_raw"   # expect ~30 Hz
```

Then the rest:

```bash
docker compose up --build -d
```

The **first** detection start takes several minutes while TensorRT builds the
engine for ssd-mobilenet-v2. The engine is cached in the `trt-cache` named
volume; subsequent starts are fast.

## Connecting Foxglove

In [Foxglove Studio](https://foxglove.dev/download) on your laptop:
*Open connection → Foxglove WebSocket →* `ws://<jetson-ip>:8765`.

Useful panels: Image (`/image_raw` or `/detectnet/overlay`), Raw Messages
(`/detectnet/detections`, `/presence/events`), Plot (`/presence/count`).

## Gotchas

- **Argus socket**: `nvarguscamerasrc` inside the container talks to the host's
  `nvargus-daemon` through `/tmp/argus_socket` (bind-mounted in compose). If the
  camera container logs `Failed to create CaptureSession`, check the daemon is
  running on the host and restart it: `sudo systemctl restart nvargus-daemon`.
- **TRT first run**: engine build takes minutes and looks like a hang — watch
  `docker compose logs -f detection`. Deleting the `trt-cache` volume forces a rebuild.
- **CycloneDDS / RMW**: every service sets `RMW_IMPLEMENTATION=rmw_cyclonedds_cpp`
  and `ROS_DOMAIN_ID=42` (YAML anchor in compose). FastDDS shared-memory transport
  breaks across container boundaries, and nodes on different RMWs fail discovery
  *silently* — if a topic list looks empty, check these two env vars first.
- **No host networking**: containers discover each other via multicast on the
  `rosnet` bridge. Topics are not visible from the Jetson host itself; use
  `docker compose exec <service> bash` to introspect.
- **ROS distro: Humble (jammy)**, not Jazzy (noble). Reason: JetPack 6.x has no
  clean Jazzy story — see notes in this repo's design history. Migration to
  Jazzy is planned when JetPack 7.2 ships Ubuntu 24.04 noble on Orin.

---
*Co-authored with Claude*
