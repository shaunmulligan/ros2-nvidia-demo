# No GPU work here: plain upstream ROS Jazzy image (noble, arm64).
FROM ros:jazzy-ros-base

ARG DEBIAN_FRONTEND=noninteractive

# vision_msgs is required so foxglove_bridge can load the schema definition
# for /detectnet/detections (vision_msgs/Detection2DArray) and serve it to clients.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ros-jazzy-rmw-cyclonedds-cpp \
        ros-jazzy-foxglove-bridge \
        ros-jazzy-vision-msgs \
 && rm -rf /var/lib/apt/lists/*

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8765

ENTRYPOINT ["/entrypoint.sh"]
# entrypoint.sh launches foxglove_bridge directly; it reads
# FOXGLOVE_REMOTE_ACCESS and FOXGLOVE_DEVICE_TOKEN env vars to decide whether
# to enable the cloud relay (both optional, defaults to local-only :8765).
CMD []
