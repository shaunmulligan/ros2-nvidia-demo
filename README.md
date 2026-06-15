# ROS2 Person-Presence Demo — Jetson Orin Nano (CSI IMX219)

Four-container ROS 2 Humble pipeline on docker-compose, all built on
NVIDIA's official `nvcr.io/nvidia/l4t-jetpack:r36.4.0` base (Ubuntu 22.04
jammy). We'll migrate to ROS2 Jazzy when JetPack 7.2 lands on Orin (Ubuntu 24.04 noble).

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

- JetPack 6.x (L4T r36.4.x), IMX219 CSI camera connected and enumerated by running the right dtbo
- Proof of Concept balenaOS running supervisor and host-extensions that support:
  - `nvargus-daemon` running on the host 
  - NVIDIA container runtime configured for balena-engine 

## Deploy

Currently needs to be deployed with v24 CLI and `balena deploy` only as `runtime` field is blocked by newer versions.

The **first** detection start takes several minutes while TensorRT builds the
engine. The engine is cached in the `trt-cache` named
volume; subsequent starts are fast.

## Connecting Foxglove

In [Foxglove Studio](https://foxglove.dev/download) on your laptop or via the web interface setup:
*Open connection → Foxglove WebSocket →* `ws://<jetson-ip>:8765`.

Useful panels: Image (`/image_raw` or `/detectnet/overlay`), Raw Messages
(`/detectnet/detections`, `/presence/events`), Plot (`/presence/count`).

## Gotchas

- **Argus socket**: `nvarguscamerasrc` inside the container talks to the host's
  `nvargus-daemon` through `/tmp/argus_socket` (bind-mounted in compose). If the
  camera container logs `Failed to create CaptureSession`, check the daemon is
  running on the host and restart it: `sudo systemctl restart nvargus-daemon`.
- **TRT first run**: engine build takes minutes and looks like a hang — watch. Deleting the `trt-cache` volume forces a rebuild.
- **CycloneDDS / RMW**: every service sets `RMW_IMPLEMENTATION=rmw_cyclonedds_cpp`
  and `ROS_DOMAIN_ID=42`. FastDDS shared-memory transport
  breaks across container boundaries, and nodes on different RMWs fail discovery
  *silently* — if a topic list looks empty, check these two env vars first.
- **No host networking**: containers discover each other via multicast on the
  `rosnet` bridge. Topics are not visible from the Jetson host itself; use
  `docker compose exec <service> bash` to introspect.
- **ROS distro: Humble (jammy)**, not Jazzy (noble). Reason: JetPack 6.x has no
  clean Jazzy story — see notes in this repo's design history. Migration to
  Jazzy is planned when JetPack 7.2 ships Ubuntu 24.04 noble on Orin.
