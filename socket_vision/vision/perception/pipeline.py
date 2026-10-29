from socket_vision.vision.perception.line_segmentation import LineSegmentationPerception


class CombinedPerception:
    def __init__(self, full_cfg):
        self.line = LineSegmentationPerception(full_cfg)

    def process(self, frame):
        lane_mask, lane_contours, lane_info = self.line.process(frame)
        detections = []
        return lane_mask, lane_contours, lane_info, detections


def create_perception(full_cfg):
    mode = str(full_cfg.get("vision", {}).get("mode", "line_segmentation")).lower()
    if mode not in {"line_segmentation", "line"}:
        raise RuntimeError(f"vision.mode={mode!r} is no longer supported; use 'line_segmentation'")
    return CombinedPerception(full_cfg)
