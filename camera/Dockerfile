FROM nvcr.io/nvidia/l4t-jetpack:r36.4.0

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=en_US.UTF-8

# Locale + apt prereqs for adding the ROS2 repo
RUN apt-get update && apt-get install -y --no-install-recommends \
        locales curl ca-certificates gnupg lsb-release \
 && locale-gen en_US.UTF-8 && update-locale LANG=en_US.UTF-8 \
 && rm -rf /var/lib/apt/lists/*

# Add the ROS2 apt repo with the current Open Robotics key
RUN curl -fsSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key -o /tmp/ros.key \
 && gpg --batch --yes --dearmor -o /usr/share/keyrings/ros-archive-keyring.gpg < /tmp/ros.key \
 && rm /tmp/ros.key \
 && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] http://packages.ros.org/ros2/ubuntu $(lsb_release -cs) main" \
        > /etc/apt/sources.list.d/ros2.list

# ROS Humble + binary gscam2 + GStreamer runtime plugins (appsink, videoconvert).
# nvarguscamerasrc and nvvidconv ship in the l4t-jetpack base's L4T multimedia stack.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ros-humble-ros-base \
        ros-humble-rmw-cyclonedds-cpp \
        ros-humble-gscam \
        ros-humble-image-transport \
        ros-humble-compressed-image-transport \
        gstreamer1.0-plugins-base \
        gstreamer1.0-plugins-good \
        gstreamer1.0-tools \
 && rm -rf /var/lib/apt/lists/*

COPY params.yaml /config/params.yaml
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

COPY run_camera.sh /run_camera.sh
RUN chmod +x /run_camera.sh
# Runs gscam_node + an image_transport republisher so /image_raw/compressed
# (JPEG) is on the bus alongside the raw stream — Foxglove subscribes to the
# compressed topic to stay within WiFi bandwidth.
ENTRYPOINT ["/entrypoint.sh"]
CMD ["/run_camera.sh"]
