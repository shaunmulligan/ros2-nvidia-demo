FROM nvcr.io/nvidia/l4t-jetpack:r36.4.0

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=en_US.UTF-8

RUN apt-get update && apt-get install -y --no-install-recommends \
        locales curl ca-certificates gnupg lsb-release \
 && locale-gen en_US.UTF-8 && update-locale LANG=en_US.UTF-8 \
 && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key -o /tmp/ros.key \
 && gpg --batch --yes --dearmor -o /usr/share/keyrings/ros-archive-keyring.gpg < /tmp/ros.key \
 && rm /tmp/ros.key \
 && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] http://packages.ros.org/ros2/ubuntu $(lsb_release -cs) main" \
        > /etc/apt/sources.list.d/ros2.list

RUN apt-get update && apt-get install -y --no-install-recommends \
        ros-humble-ros-base \
        ros-humble-rmw-cyclonedds-cpp \
        ros-humble-vision-msgs \
 && rm -rf /var/lib/apt/lists/*

COPY presence_node.py /app/presence_node.py
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
CMD ["python3", "/app/presence_node.py"]
