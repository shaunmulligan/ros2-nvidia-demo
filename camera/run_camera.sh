#!/usr/bin/env bash
# gscam_node + image_transport_plugins auto-publishes JPEG/Theora siblings under
# camera/image_raw/* — no separate republisher needed. We remap the base topic
# to /image_raw; the compressed sibling stays at /camera/image_raw/compressed
# (gscam's image_transport advertises siblings off the unremapped base name).
set -e
exec ros2 run gscam gscam_node --ros-args \
    -r __node:=gscam_publisher \
    -r camera/image_raw:=/image_raw \
    -r camera/camera_info:=/camera_info \
    --params-file /config/params.yaml
