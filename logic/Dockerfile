# No GPU work here: plain upstream ROS Jazzy image (noble, arm64).
FROM ros:jazzy-ros-base

ARG DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        ros-jazzy-rmw-cyclonedds-cpp \
        ros-jazzy-vision-msgs \
 && rm -rf /var/lib/apt/lists/*

COPY presence_node.py /app/presence_node.py
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
CMD ["python3", "/app/presence_node.py"]
