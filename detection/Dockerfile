# Stage 1: export yolo26s.pt -> yolo26s.onnx using ultralytics on CPU.
# Discarded once the runtime stage copies the artifact out.
FROM python:3.11-slim-bookworm AS exporter

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 libglib2.0-0 ca-certificates curl \
 && rm -rf /var/lib/apt/lists/*

# ultralytics pulls torch (cpu) + onnx + onnxslim automatically on arm64.
RUN pip install --no-cache-dir 'ultralytics>=8.3.0'

WORKDIR /export
# ultralytics auto-downloads the .pt on first run, then writes yolo26s.onnx
# next to it. Pinning opset=17 keeps the graph compatible with TRT 10.x parser.
RUN yolo export model=yolo26s.pt format=onnx imgsz=640 opset=17 simplify=True \
 && test -f yolo26s.onnx

# Stage 2: runtime — same l4t-jetpack base as before. TensorRT 10.x Python
# bindings come preinstalled; we still build the FP16 engine on first run
# (cached to the trt-cache volume) but no longer need network access for it.
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

# ROS Humble + python deps for the detection node. TensorRT 10.x Python bindings
# are already preinstalled in the l4t-jetpack base.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ros-humble-ros-base \
        ros-humble-rmw-cyclonedds-cpp \
        ros-humble-vision-msgs \
        ros-humble-cv-bridge \
        python3-opencv \
        python3-pip \
 && rm -rf /var/lib/apt/lists/*

# pycuda 2026.1 uses `np.dtype[Any]` typing which needs numpy >=1.22;
# jammy's apt python3-numpy is 1.21.5. Upgrade via pip first, then install pycuda.
RUN pip3 install --no-cache-dir --upgrade 'numpy>=1.22,<2' \
 && pip3 install --no-cache-dir pycuda

# Bundle the exported ONNX so detect_node never hits the network at runtime.
COPY --from=exporter /export/yolo26s.onnx /opt/models/yolo26s.onnx

COPY detect_node.py /app/detect_node.py
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
CMD ["python3", "/app/detect_node.py"]
