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

# balena_supervisor_msgs has no apt package, and foxglove_bridge cannot
# advertise a topic whose type support it cannot load locally -- same reason
# vision_msgs is installed above. Without this, /balena_supervisor/device_state
# and /balena_supervisor/app_state are discovered and then never offered to
# clients. /diagnostics is unaffected (diagnostic_msgs ships in ros-base).
#
# Pinned to the commit the supervisor block image itself was built from: the
# interface definitions must match the node publishing them. The package lives
# only on a branch so far, so this is a SHA rather than a tag -- move it to a
# tag once the interfaces land on that repo's main.
ARG SUPERVISOR_MSGS_REF=6ed2f32c6a0b7cf1b7dcad02fd02d59de6352f0d
RUN . /opt/ros/jazzy/setup.sh \
 && git clone -q https://github.com/balenasolutions/ros-balena-supervisor-msgs.git \
        /ros2_ws/src/balena_supervisor_msgs \
 && git -C /ros2_ws/src/balena_supervisor_msgs checkout -q "${SUPERVISOR_MSGS_REF}" \
 && test -f /ros2_ws/src/balena_supervisor_msgs/package.xml \
 && cd /ros2_ws \
 && colcon build --merge-install --packages-select balena_supervisor_msgs \
        --cmake-args -DCMAKE_BUILD_TYPE=Release \
 && test -d /ros2_ws/install/share/balena_supervisor_msgs \
 && rm -rf build log src

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8765

ENTRYPOINT ["/entrypoint.sh"]
# entrypoint.sh launches foxglove_bridge directly; it reads
# FOXGLOVE_REMOTE_ACCESS and FOXGLOVE_DEVICE_TOKEN env vars to decide whether
# to enable the cloud relay (both optional, defaults to local-only :8765).
CMD []
