from pathlib import Path

import cv2
import numpy as np

def _find_project_root() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "global_config.json").exists() and (parent / "config_loader.py").exists():
            return parent
    # Fallback to previous behavior if markers are not found.
    return current.parents[2]


PROJECT_ROOT = _find_project_root()


def _resolve_path(path_value):
    if not path_value:
        return None
    path = Path(path_value)
    if path.is_absolute():
        return path
    # Resolve model paths relative to socket_vision project root.
    return PROJECT_ROOT / path


def _sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


def _set_preferred_target(net, cfg):
    if not bool(cfg.get("dnn_prefer_cuda", False)):
        return
    try:
        net.setPreferableBackend(cv2.dnn.DNN_BACKEND_CUDA)
        target = cv2.dnn.DNN_TARGET_CUDA_FP16 if bool(cfg.get("dnn_fp16", True)) else cv2.dnn.DNN_TARGET_CUDA
        net.setPreferableTarget(target)
    except Exception as exc:
        print(f"[line-seg] CUDA DNN target unavailable, using default OpenCV target: {exc}")


def _as_single_output(outputs):
    if isinstance(outputs, (tuple, list)):
        return outputs[0]
    return outputs


def _decode_binary_masks(raw_mask, frame_shape, mask_threshold, per_channel_thresholds=None):
    arr = np.asarray(raw_mask, dtype=np.float32)
    if arr.ndim == 4:
        arr = arr[0]  # [C,H,W]
    elif arr.ndim == 2:
        arr = arr[None, ...]
    elif arr.ndim != 3:
        arr = np.squeeze(arr)
        if arr.ndim == 2:
            arr = arr[None, ...]
    masks = []
    height, width = frame_shape[:2]
    thresholds = per_channel_thresholds or {}
    for c in range(arr.shape[0]):
        ch = arr[c]
        if float(ch.min()) < 0.0 or float(ch.max()) > 1.0:
            ch = _sigmoid(ch)
        thr = float(thresholds.get(c, mask_threshold))
        mask = (ch >= thr).astype(np.uint8) * 255
        mask = cv2.resize(mask, (width, height), interpolation=cv2.INTER_NEAREST)
        masks.append(mask)
    return masks


def _harden_track_mask(mask, cfg):
    if not bool(cfg.get("track_mask_harden_enabled", True)):
        return mask

    out = mask.copy()
    kernel_size = int(cfg.get("track_mask_harden_kernel", 5))
    kernel_size = max(1, kernel_size)
    if kernel_size % 2 == 0:
        kernel_size += 1
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))

    close_iter = max(0, int(cfg.get("track_mask_close_iter", 2)))
    open_iter = max(0, int(cfg.get("track_mask_open_iter", 1)))
    if close_iter > 0:
        out = cv2.morphologyEx(out, cv2.MORPH_CLOSE, kernel, iterations=close_iter)
    if open_iter > 0:
        out = cv2.morphologyEx(out, cv2.MORPH_OPEN, kernel, iterations=open_iter)

    min_component_pixels = max(0, int(cfg.get("track_mask_min_component_pixels", 0)))
    if min_component_pixels <= 0:
        return out

    binary = (out > 0).astype(np.uint8)
    n_labels, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
    cleaned = np.zeros_like(out, dtype=np.uint8)
    for label_id in range(1, int(n_labels)):
        area = int(stats[label_id, cv2.CC_STAT_AREA])
        if area >= min_component_pixels:
            cleaned[labels == label_id] = 255
    return cleaned


def _center_from_raw_mask(track_mask_raw, box_mask_raw, frame_shape, cfg, source="line_segmentation_raw"):
    height, width = frame_shape[:2]
    frame_center_x = float(width) / 2.0

    roi_start_ratio = float(cfg.get("track_roi_start_ratio", 0.5))
    roi_end_ratio = float(cfg.get("track_roi_end_ratio", 1.0))
    roi_start_y = max(0, min(height - 1, int(roi_start_ratio * height)))
    roi_end_y = max(roi_start_y + 1, min(height, int(roi_end_ratio * height)))

    roi = track_mask_raw[roi_start_y:roi_end_y, :]
    ys, xs = np.where(roi > 0)
    min_pixels = int(cfg.get("line_center_min_pixels", 20))

    has_center = int(xs.size) >= min_pixels
    lane_center_x = float(xs.mean()) if has_center else None
    center_offset_px = (lane_center_x - frame_center_x) if has_center else None

    lane_info = {
        "source": source,
        "has_center": bool(has_center),
        "center_offset_px": center_offset_px,
        "lane_center_x": lane_center_x,
        "frame_center_x": frame_center_x,
        "left_boundary_x": None,
        "right_boundary_x": None,
        "roi_start_y": int(roi_start_y),
        "roi_end_y": int(roi_end_y - 1),
        "tape_points": [],
        "track_mask": track_mask_raw,
        "box_mask": box_mask_raw,
    }
    # No geometric postprocess: keep raw mask and no contours.
    return track_mask_raw, [], lane_info


class LineSegmentationDnn:
    def __init__(self, model_path, cfg):
        self.model_path = Path(model_path)
        self.cfg = cfg
        self.input_width = int(cfg.get("line_input_width", 320))
        self.input_height = int(cfg.get("line_input_height", 192))
        self.track_channel = int(cfg.get("line_track_channel", cfg.get("line_output_channel", 0)))
        self.box_channel = int(cfg.get("line_box_channel", 1))
        self.mask_threshold = float(cfg.get("segmentation_threshold", 0.5))
        self.track_mask_threshold = float(cfg.get("track_segmentation_threshold", self.mask_threshold))
        self.box_mask_threshold = float(cfg.get("box_segmentation_threshold", self.mask_threshold))
        self.net = cv2.dnn.readNetFromONNX(str(self.model_path))
        _set_preferred_target(self.net, cfg)

    def _forward(self, frame):
        blob = cv2.dnn.blobFromImage(
            frame,
            scalefactor=1.0 / 255.0,
            size=(self.input_width, self.input_height),
            mean=(0, 0, 0),
            swapRB=True,
            crop=False,
        )
        self.net.setInput(blob)
        output_names = self.net.getUnconnectedOutLayersNames()
        return _as_single_output(self.net.forward(output_names))

    def _decode_masks(self, raw_mask, frame_shape):
        thresholds = {
            int(self.track_channel): self.track_mask_threshold,
            int(self.box_channel): self.box_mask_threshold,
        }
        return _decode_binary_masks(raw_mask, frame_shape, self.mask_threshold, per_channel_thresholds=thresholds)

    def process(self, frame):
        raw_mask = self._forward(frame)
        masks = self._decode_masks(raw_mask, frame.shape)
        track_idx = max(0, min(self.track_channel, len(masks) - 1))
        box_idx = max(0, min(self.box_channel, len(masks) - 1))
        track_mask_raw = masks[track_idx]
        track_mask_raw = _harden_track_mask(track_mask_raw, self.cfg)
        box_mask_raw = masks[box_idx] if len(masks) > 1 else np.zeros_like(track_mask_raw)
        return _center_from_raw_mask(track_mask_raw, box_mask_raw, frame.shape, self.cfg, source="line_segmentation_raw")


class LineSegmentationOrt:
    def __init__(self, model_path, cfg):
        self.model_path = Path(model_path)
        self.cfg = cfg
        self.input_width = int(cfg.get("line_input_width", 320))
        self.input_height = int(cfg.get("line_input_height", 192))
        self.track_channel = int(cfg.get("line_track_channel", cfg.get("line_output_channel", 0)))
        self.box_channel = int(cfg.get("line_box_channel", 1))
        self.mask_threshold = float(cfg.get("segmentation_threshold", 0.5))
        self.track_mask_threshold = float(cfg.get("track_segmentation_threshold", self.mask_threshold))
        self.box_mask_threshold = float(cfg.get("box_segmentation_threshold", self.mask_threshold))
        import onnxruntime as ort

        self.session = ort.InferenceSession(str(self.model_path), providers=["CPUExecutionProvider"])
        self.input_name = self.session.get_inputs()[0].name

    def _forward(self, frame):
        resized = cv2.resize(frame, (self.input_width, self.input_height), interpolation=cv2.INTER_AREA)
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        x = rgb.astype(np.float32) / 255.0
        x = np.transpose(x, (2, 0, 1))[None, ...]
        outputs = self.session.run(None, {self.input_name: x})
        return _as_single_output(outputs)

    def process(self, frame):
        raw_mask = self._forward(frame)
        thresholds = {
            int(self.track_channel): self.track_mask_threshold,
            int(self.box_channel): self.box_mask_threshold,
        }
        masks = _decode_binary_masks(raw_mask, frame.shape, self.mask_threshold, per_channel_thresholds=thresholds)
        track_idx = max(0, min(self.track_channel, len(masks) - 1))
        box_idx = max(0, min(self.box_channel, len(masks) - 1))
        track_mask_raw = masks[track_idx]
        track_mask_raw = _harden_track_mask(track_mask_raw, self.cfg)
        box_mask_raw = masks[box_idx] if len(masks) > 1 else np.zeros_like(track_mask_raw)
        return _center_from_raw_mask(track_mask_raw, box_mask_raw, frame.shape, self.cfg, source="line_segmentation_raw")


class LineSegmentationPerception:
    def __init__(self, full_cfg):
        self.cfg = full_cfg
        self.vis_cfg = full_cfg["vision"]
        self.models_cfg = full_cfg.get("models", {})
        self.model = None

        engine_path = _resolve_path(self.models_cfg.get("line_engine"))
        if engine_path is not None and engine_path.exists():
            print("[line-seg] TensorRT engine configured. Runtime uses ONNX unless OpenCV can load the engine directly.")

        onnx_path = _resolve_path(self.models_cfg.get("line_onnx"))
        if onnx_path is not None and onnx_path.exists():
            try:
                self.model = LineSegmentationDnn(onnx_path, self.vis_cfg)
                print(f"[line-seg] loaded ONNX with OpenCV DNN: {onnx_path}")
            except Exception as dnn_exc:
                self.model = LineSegmentationOrt(onnx_path, self.vis_cfg)
                print(f"[line-seg] loaded ONNX with ONNX Runtime: {onnx_path} (OpenCV DNN failed: {dnn_exc})")
        else:
            raise RuntimeError(f"Line segmentation ONNX not found: {onnx_path}")

    def process(self, frame):
        return self.model.process(frame)
