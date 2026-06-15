#!/usr/bin/env python3
# YOLO26s object detection via TensorRT, publishing vision_msgs/Detection2DArray.
#
# Subscribes: /image_raw         (sensor_msgs/Image, rgb8)
# Publishes:  /detectnet/detections (vision_msgs/Detection2DArray)
#             /detectnet/overlay    (sensor_msgs/Image, rgb8)
#
# The ONNX is baked into the image at /opt/models/yolo26s.onnx (exported from
# yolo26s.pt during docker build). On first run we build an FP16 TensorRT engine
# at /usr/local/bin/networks/yolo26s/yolo26s.fp16.engine — that path is on the
# trt-cache named volume so the engine survives container restarts.

import os
import shutil
import sys

import numpy as np
import cv2

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import CompressedImage, Image
from vision_msgs.msg import (
    BoundingBox2D, Detection2D, Detection2DArray, ObjectHypothesisWithPose,
)
from cv_bridge import CvBridge

import tensorrt as trt
import pycuda.driver as cuda
import pycuda.autoinit  # noqa: F401 — initializes the CUDA context as a side-effect

BUNDLED_ONNX = "/opt/models/yolo26s.onnx"
NETWORKS_DIR = "/usr/local/bin/networks/yolo26s"
ONNX_PATH = f"{NETWORKS_DIR}/yolo26s.onnx"
ENGINE_PATH = f"{NETWORKS_DIR}/yolo26s.fp16.engine"
INPUT_HW = 640
CONF_DEFAULT = 0.4

COCO_CLASSES = [
    'person', 'bicycle', 'car', 'motorcycle', 'airplane', 'bus', 'train',
    'truck', 'boat', 'traffic light', 'fire hydrant', 'stop sign',
    'parking meter', 'bench', 'bird', 'cat', 'dog', 'horse', 'sheep', 'cow',
    'elephant', 'bear', 'zebra', 'giraffe', 'backpack', 'umbrella', 'handbag',
    'tie', 'suitcase', 'frisbee', 'skis', 'snowboard', 'sports ball', 'kite',
    'baseball bat', 'baseball glove', 'skateboard', 'surfboard',
    'tennis racket', 'bottle', 'wine glass', 'cup', 'fork', 'knife', 'spoon',
    'bowl', 'banana', 'apple', 'sandwich', 'orange', 'broccoli', 'carrot',
    'hot dog', 'pizza', 'donut', 'cake', 'chair', 'couch', 'potted plant',
    'bed', 'dining table', 'toilet', 'tv', 'laptop', 'mouse', 'remote',
    'keyboard', 'cell phone', 'microwave', 'oven', 'toaster', 'sink',
    'refrigerator', 'book', 'clock', 'vase', 'scissors', 'teddy bear',
    'hair drier', 'toothbrush',
]


def build_engine(onnx_path: str, engine_path: str) -> None:
    logger = trt.Logger(trt.Logger.INFO)
    builder = trt.Builder(logger)
    network = builder.create_network(
        1 << int(trt.NetworkDefinitionCreationFlag.EXPLICIT_BATCH))
    parser = trt.OnnxParser(network, logger)
    with open(onnx_path, 'rb') as f:
        if not parser.parse(f.read()):
            errs = '\n'.join(
                parser.get_error(i).desc() for i in range(parser.num_errors))
            raise RuntimeError(f"ONNX parse failed:\n{errs}")
    config = builder.create_builder_config()
    # Orin Nano has 8 GB shared CPU/GPU memory; with the camera service running
    # we can't afford a 1 GiB workspace. 256 MiB is enough for yolo26s FP16.
    config.set_memory_pool_limit(trt.MemoryPoolType.WORKSPACE, 1 << 28)
    if builder.platform_has_fast_fp16:
        config.set_flag(trt.BuilderFlag.FP16)
    serialized = builder.build_serialized_network(network, config)
    if serialized is None:
        raise RuntimeError("TensorRT engine build returned None")
    with open(engine_path, 'wb') as f:
        f.write(serialized)


def ensure_engine() -> None:
    os.makedirs(NETWORKS_DIR, exist_ok=True)
    if not os.path.exists(ONNX_PATH):
        shutil.copyfile(BUNDLED_ONNX, ONNX_PATH)
    if not os.path.exists(ENGINE_PATH):
        print("[detect_node] building TensorRT engine (first run, ~minutes)",
              flush=True)
        build_engine(ONNX_PATH, ENGINE_PATH)
        print(f"[detect_node] engine cached at {ENGINE_PATH}", flush=True)


def letterbox(img: np.ndarray, new_hw: int = INPUT_HW):
    h0, w0 = img.shape[:2]
    r = min(new_hw / h0, new_hw / w0)
    new_h, new_w = int(round(h0 * r)), int(round(w0 * r))
    dh, dw = (new_hw - new_h) // 2, (new_hw - new_w) // 2
    resized = cv2.resize(img, (new_w, new_h))
    out = np.full((new_hw, new_hw, 3), 114, dtype=img.dtype)
    out[dh:dh + new_h, dw:dw + new_w] = resized
    return out, r, (dw, dh)


class YoloDetect(Node):
    def __init__(self):
        super().__init__('detectnet')
        self.declare_parameter('threshold', CONF_DEFAULT)
        self.bridge = CvBridge()

        ensure_engine()
        trt_logger = trt.Logger(trt.Logger.WARNING)
        runtime = trt.Runtime(trt_logger)
        with open(ENGINE_PATH, 'rb') as f:
            self.engine = runtime.deserialize_cuda_engine(f.read())
        self.trt_context = self.engine.create_execution_context()

        # TRT 10 tensor API
        self.input_name = self.engine.get_tensor_name(0)
        self.output_name = self.engine.get_tensor_name(1)
        self.input_shape = tuple(self.engine.get_tensor_shape(self.input_name))
        self.output_shape = tuple(self.engine.get_tensor_shape(self.output_name))
        self.trt_context.set_input_shape(self.input_name, self.input_shape)

        def _np_dtype(trt_dt):
            return {
                trt.DataType.FLOAT: np.float32,
                trt.DataType.HALF: np.float16,
            }[trt_dt]
        self.in_np_dtype = _np_dtype(self.engine.get_tensor_dtype(self.input_name))
        self.out_np_dtype = _np_dtype(self.engine.get_tensor_dtype(self.output_name))
        in_bytes = int(np.prod(self.input_shape)) * np.dtype(self.in_np_dtype).itemsize
        out_bytes = int(np.prod(self.output_shape)) * np.dtype(self.out_np_dtype).itemsize
        self.d_input = cuda.mem_alloc(in_bytes)
        self.d_output = cuda.mem_alloc(out_bytes)
        self.h_output = np.empty(self.output_shape, dtype=self.out_np_dtype)
        self.trt_context.set_tensor_address(self.input_name, int(self.d_input))
        self.trt_context.set_tensor_address(self.output_name, int(self.d_output))
        self.stream = cuda.Stream()

        self.det_pub = self.create_publisher(
            Detection2DArray, '/detectnet/detections', 10)
        self.overlay_pub = self.create_publisher(Image, '/detectnet/overlay', 10)
        # JPEG sibling for Foxglove — raw rgb8 at 30 Hz saturates a WiFi link.
        self.overlay_compressed_pub = self.create_publisher(
            CompressedImage, '/detectnet/overlay/compressed', 10)
        self.create_subscription(Image, '/image_raw', self.on_image, 10)
        self.get_logger().info(
            f"yolo26s detect ready (input {self.input_shape}, "
            f"output {self.output_shape})")

    def on_image(self, msg: Image) -> None:
        img = self.bridge.imgmsg_to_cv2(msg, desired_encoding='rgb8')
        h0, w0 = img.shape[:2]
        padded, scale, (dx, dy) = letterbox(img)
        nchw = padded.transpose(2, 0, 1)[np.newaxis].astype(np.float32) / 255.0
        nchw = np.ascontiguousarray(nchw.astype(self.in_np_dtype))

        cuda.memcpy_htod_async(self.d_input, nchw, self.stream)
        self.trt_context.execute_async_v3(self.stream.handle)
        cuda.memcpy_dtoh_async(self.h_output, self.d_output, self.stream)
        self.stream.synchronize()

        # YOLO26 end2end head output: (1, 300, 6) already NMS-filtered.
        # Each row: [x1, y1, x2, y2, conf, class_idx] in 640-pixel input space.
        # Rows past the true detection count are zero-padded — the confidence
        # threshold below filters them out alongside low-score detections.
        preds = self.h_output[0].astype(np.float32)
        boxes_xyxy = preds[:, :4]
        confs = preds[:, 4]
        class_ids = preds[:, 5].astype(np.int32)

        threshold = float(self.get_parameter('threshold').value)
        mask = confs > threshold
        boxes_xyxy = boxes_xyxy[mask].copy()
        confs = confs[mask]
        class_ids = class_ids[mask]
        if len(boxes_xyxy) == 0:
            self._publish(msg.header, [], img)
            return

        # Undo letterbox: 640-space -> original image pixel space.
        boxes_xyxy[:, [0, 2]] = (boxes_xyxy[:, [0, 2]] - dx) / scale
        boxes_xyxy[:, [1, 3]] = (boxes_xyxy[:, [1, 3]] - dy) / scale
        boxes_xyxy[:, [0, 2]] = boxes_xyxy[:, [0, 2]].clip(0, w0)
        boxes_xyxy[:, [1, 3]] = boxes_xyxy[:, [1, 3]].clip(0, h0)

        detections = [
            (boxes_xyxy[i], float(confs[i]), int(class_ids[i]))
            for i in range(len(boxes_xyxy))
        ]
        self._publish(msg.header, detections, img)

    def _publish(self, header, detections, img: np.ndarray) -> None:
        out = Detection2DArray()
        out.header = header
        overlay = img.copy()
        for (x1, y1, x2, y2), conf, cid in detections:
            d = Detection2D()
            d.header = header
            d.bbox.center.position.x = float((x1 + x2) / 2)
            d.bbox.center.position.y = float((y1 + y2) / 2)
            d.bbox.size_x = float(x2 - x1)
            d.bbox.size_y = float(y2 - y1)
            hyp = ObjectHypothesisWithPose()
            hyp.hypothesis.class_id = str(cid)
            hyp.hypothesis.score = float(conf)
            d.results.append(hyp)
            out.detections.append(d)
            label = f"{COCO_CLASSES[cid] if cid < len(COCO_CLASSES) else cid} {conf:.2f}"
            cv2.rectangle(overlay, (int(x1), int(y1)), (int(x2), int(y2)),
                          (0, 255, 0), 2)
            cv2.putText(overlay, label, (int(x1), max(0, int(y1) - 5)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
        self.det_pub.publish(out)
        ov_msg = self.bridge.cv2_to_imgmsg(overlay, encoding='rgb8')
        ov_msg.header = header
        self.overlay_pub.publish(ov_msg)
        bgr = cv2.cvtColor(overlay, cv2.COLOR_RGB2BGR)
        ok, jpeg = cv2.imencode('.jpg', bgr, [cv2.IMWRITE_JPEG_QUALITY, 75])
        if ok:
            cmsg = CompressedImage()
            cmsg.header = header
            cmsg.format = 'jpeg'
            cmsg.data = jpeg.tobytes()
            self.overlay_compressed_pub.publish(cmsg)


def main():
    rclpy.init()
    try:
        rclpy.spin(YoloDetect())
    except KeyboardInterrupt:
        pass
    finally:
        rclpy.shutdown()


if __name__ == '__main__':
    sys.exit(main())
