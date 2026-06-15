#!/usr/bin/env bash
set -e
source /opt/ros/humble/setup.bash

# Build foxglove_bridge ROS args from env. FOXGLOVE_REMOTE_ACCESS=true enables
# the cloud relay (no inbound port needed) and requires FOXGLOVE_DEVICE_TOKEN
# from foxglove.dev → Devices. With both unset, the bridge serves only the
# local websocket on :8765, same as the previous behaviour.
args=(
  --ros-args
  -p "port:=8765"
  -p "address:=0.0.0.0"
  -p "sysinfo:=true"
)

case "${FOXGLOVE_REMOTE_ACCESS:-}" in
  1|true|TRUE|True)
    if [[ -z "${FOXGLOVE_DEVICE_TOKEN:-}" ]]; then
      echo "[viz] FOXGLOVE_REMOTE_ACCESS=true but FOXGLOVE_DEVICE_TOKEN is empty — cloud relay will fail to authenticate" >&2
    fi
    args+=(
      -p "remote_access:=true"
      -p "device_token:=${FOXGLOVE_DEVICE_TOKEN:-}"
    )
    ;;
esac

exec ros2 run foxglove_bridge foxglove_bridge "${args[@]}"
