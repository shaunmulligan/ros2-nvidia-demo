# Single multi-stage Dockerfile for the two Jetson services. docker-compose
# selects a stage per service with build.target; `base` is shared.
#
# NVIDIA stopped publishing nvcr.io/nvidia/l4t-jetpack after r36.4.0, so the
# GPU bits are installed from the L4T r39.2 (JetPack 7.2) apt repo, following
# NVIDIA's public recipe: https://gitlab.com/nvidia/container-images/l4t-jetpack
#
# Size matters: this repo deploys over a slow uplink. Each stage installs only
# what it loads. libnvinfer10 alone is 2.9 GB, the full CUDA library set 1.9 GB.
#
# Note: the balenaCloud builder builds each compose service independently, so
# `base` is built once per service there. Layer cache normally absorbs this.

# ---------------------------------------------------------------------------
# base: noble + ROS Jazzy + the two apt repos. No GPU libraries.
FROM nvcr.io/nvidia/base/ubuntu:noble-20260730.1 AS base

ARG L4T_RELEASE=r39.2
ARG DEBIAN_FRONTEND=noninteractive
ENV LANG=en_US.UTF-8

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl gnupg2 locales lsb-release wget \
 && locale-gen en_US.UTF-8 && update-locale LANG=en_US.UTF-8 \
 && rm -rf /var/lib/apt/lists/*

# L4T apt repo. Kept in the image so later stages can add JetPack packages.
RUN wget -qP /etc/apt/trusted.gpg.d https://repo.download.nvidia.com/jetson/jetson-ota-public.asc \
 && wget -qP /etc/apt/preferences.d https://repo.download.nvidia.com/jetson/nvidia-repo-pin-600 \
 && echo "deb https://repo.download.nvidia.com/jetson/common ${L4T_RELEASE} main" \
        > /etc/apt/sources.list.d/nvidia-l4t-apt-source.list

# ROS 2 apt repo with the current Open Robotics key. noble -> Jazzy.
RUN curl -fsSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key \
        | gpg --batch --yes --dearmor -o /usr/share/keyrings/ros-archive-keyring.gpg \
 && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] http://packages.ros.org/ros2/ubuntu $(lsb_release -cs) main" \
        > /etc/apt/sources.list.d/ros2.list

RUN apt-get update && apt-get install -y --no-install-recommends \
        ros-jazzy-ros-base \
        ros-jazzy-rmw-cyclonedds-cpp \
 && rm -rf /var/lib/apt/lists/*

# Both derived services run with `runtime: nvidia`; these select the host mounts.
ENV NVIDIA_VISIBLE_DEVICES=all \
    NVIDIA_DRIVER_CAPABILITIES=all

# ---------------------------------------------------------------------------
# camera: GStreamer + nvarguscamerasrc/nvvidconv + gscam. No CUDA: the NVIDIA
# plugins link only L4T libraries, which the container runtime bind-mounts
# from the host.
FROM base AS camera

ARG DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        gstreamer1.0-plugins-base \
        gstreamer1.0-plugins-good \
        gstreamer1.0-plugins-bad \
        gstreamer1.0-tools \
        libdrm2 libegl1 libgles2 libglvnd0 libwayland-client0 libwayland-egl1 \
        ros-jazzy-gscam \
        ros-jazzy-image-transport \
        ros-jazzy-compressed-image-transport \
 && rm -rf /var/lib/apt/lists/*

# nvidia-l4t-gstreamer: extracted rather than installed. Its declared deps
# (nvidia-l4t-camera, -multimedia, -cuda, ...) are the host-mounted libraries,
# exactly as in NVIDIA's own Dockerfile.
RUN apt-get update && apt-get download nvidia-l4t-gstreamer \
 && dpkg-deb -R ./nvidia-l4t-gstreamer_*_arm64.deb ./gst \
 && cp -r ./gst/usr/bin/* /usr/bin/ \
 && cp -r ./gst/usr/lib/* /usr/lib/ \
 && rm -rf ./nvidia-l4t-gstreamer_*_arm64.deb ./gst /var/lib/apt/lists/* \
 && echo "/usr/lib/aarch64-linux-gnu/tegra" > /etc/ld.so.conf.d/nvidia-tegra.conf \
 && echo "/usr/lib/aarch64-linux-gnu/tegra-egl" >> /etc/ld.so.conf.d/nvidia-tegra.conf \
 && ldconfig

COPY camera/params.yaml /config/params.yaml
COPY camera/entrypoint.sh /entrypoint.sh
COPY camera/run_camera.sh /run_camera.sh
RUN chmod +x /entrypoint.sh /run_camera.sh

# Runs gscam_node; image_transport publishes /camera/image_raw/compressed (JPEG)
# alongside the raw stream so Foxglove stays within WiFi bandwidth.
ENTRYPOINT ["/entrypoint.sh"]
CMD ["/run_camera.sh"]

# ---------------------------------------------------------------------------
# detection: TensorRT 10.16 runtime + the CUDA libraries it and pycuda load.
# libcuda itself comes from the host mount. TensorRT 10 loads cuBLAS/cuDNN
# lazily and only when enabled, so they are left out.
FROM base AS detection

ARG DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        cuda-cudart-13-2 \
        libcurand-13-2 \
        nvidia-tensorrt \
        python3-libnvinfer \
        ros-jazzy-vision-msgs \
        ros-jazzy-cv-bridge \
        python3-opencv \
        python3-numpy \
        python3-pip \
 && rm -rf /var/lib/apt/lists/*

# pycuda has no arm64 wheel; build it from source, then drop the build-only
# packages in the same layer. pycuda's configure locates CUDA only through
# `nvcc` on PATH on Linux (no CUDA_ROOT env override), so cuda-nvcc is a
# build dep even though nothing here compiles device code.
# python3-dev is deliberately NOT purged: ros-jazzy-fastrtps depends on it, and
# purging it makes apt remove the whole ROS tree.
# --break-system-packages: noble enforces PEP 668.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential python3-dev \
        cuda-nvcc-13-2 cuda-cudart-dev-13-2 cuda-driver-dev-13-2 cuda-profiler-api-13-2 libcurand-dev-13-2 \
 && PATH=/usr/local/cuda/bin:$PATH pip3 install --no-cache-dir --break-system-packages pycuda \
 && apt-get purge -y --auto-remove \
        build-essential \
        cuda-nvcc-13-2 cuda-cudart-dev-13-2 cuda-driver-dev-13-2 cuda-profiler-api-13-2 libcurand-dev-13-2 \
 && test -d /opt/ros/jazzy \
 && rm -rf /var/lib/apt/lists/*

ENV CUDA_HOME=/usr/local/cuda \
    PATH=/usr/local/cuda/bin:$PATH \
    LD_LIBRARY_PATH=/usr/local/cuda/lib64

# yolo26s.onnx is exported once from yolo26s.pt via ultralytics and committed
# to the repo. Doing this in a builder stage would pull torch (~700 MB wheel,
# ~2 GB installed) into the balenaCloud builder and OOM the arm64 build job.
# To re-export: `cd detection && uv run --with 'ultralytics>=8.3.0' --no-project
#                -- yolo export model=yolo26s.pt format=onnx imgsz=640 opset=17
#                simplify=True`
COPY detection/yolo26s.onnx /opt/models/yolo26s.onnx

COPY detection/detect_node.py /app/detect_node.py
COPY detection/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
CMD ["python3", "/app/detect_node.py"]
