import time

import cv2
import numpy as np


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _lane_steering_from_offset(offset_px, frame_half, ctrl_cfg, max_steering):
    if offset_px is None:
        return 0.0
    offset_norm = float(offset_px / frame_half)
    deadband = float(ctrl_cfg.get("auto_center_deadband", 0.05))
    if abs(offset_norm) <= deadband:
        return 0.0
    steering_kp = float(ctrl_cfg.get("auto_steering_kp", 0.9))
    steering_curve_gain = float(ctrl_cfg.get("auto_steering_curve_gain", 0.0))
    signed_curve = offset_norm * abs(offset_norm)
    return _clamp(
        (offset_norm * steering_kp) + (signed_curve * steering_curve_gain),
        -max_steering,
        max_steering,
    )


def _obstacle_risk(frame_shape, detections, ctrl_cfg):
    if not bool(ctrl_cfg.get("obstacle_avoidance_enabled", True)):
        return None
    if not detections:
        return None

    height, width = frame_shape[:2]
    roi_top = int(float(ctrl_cfg.get("obstacle_roi_top_ratio", 0.55)) * height)
    roi_left = int(float(ctrl_cfg.get("obstacle_roi_left_ratio", 0.2)) * width)
    roi_right = int(float(ctrl_cfg.get("obstacle_roi_right_ratio", 0.8)) * width)
    min_area_ratio = float(ctrl_cfg.get("obstacle_min_area_ratio", 0.015))
    emergency_area_ratio = float(ctrl_cfg.get("obstacle_emergency_area_ratio", 0.06))
    area_span = max(1e-6, emergency_area_ratio - min_area_ratio)

    frame_area = float(max(1, width * height))
    best = None

    for det in detections:
        x1, y1, x2, y2 = det["box"]
        cx = (x1 + x2) / 2.0
        area_ratio = max(0.0, float((x2 - x1) * (y2 - y1)) / frame_area)
        in_front_roi = (y2 >= roi_top) and (roi_left <= cx <= roi_right)
        if not in_front_roi or area_ratio < min_area_ratio:
            continue
        urgency = _clamp((area_ratio - min_area_ratio) / area_span, 0.0, 1.0)
        candidate = {
            "label": det.get("label", "obstacle"),
            "score": float(det.get("score", 0.0)),
            "area_ratio": area_ratio,
            "box": det["box"],
            "emergency": area_ratio >= emergency_area_ratio,
            "urgency": float(urgency),
        }
        if best is None or candidate["area_ratio"] > best["area_ratio"]:
            best = candidate
    return best


def _box_mask_obstacle_risk(frame_shape, lane_info, ctrl_cfg):
    if not bool(ctrl_cfg.get("obstacle_mask_enabled", True)):
        return None
    box_mask = lane_info.get("box_mask")
    if box_mask is None:
        return None

    height, width = frame_shape[:2]
    roi_top = int(float(ctrl_cfg.get("obstacle_mask_roi_top_ratio", ctrl_cfg.get("obstacle_roi_top_ratio", 0.55))) * height)
    roi_top = max(0, min(height - 1, roi_top))
    roi = box_mask[roi_top:height, :]
    if roi.size == 0:
        return None

    ys, xs = np.where(roi > 0)
    pixel_count = int(xs.size)
    min_pixels = int(ctrl_cfg.get("obstacle_mask_min_pixels", 60))
    if pixel_count < min_pixels:
        return None

    roi_bin = (roi > 0).astype(np.uint8)
    n_labels, _, stats, _ = cv2.connectedComponentsWithStats(roi_bin, connectivity=8)
    min_component_pixels = int(ctrl_cfg.get("obstacle_mask_min_component_pixels", min_pixels))
    min_width_px = int(ctrl_cfg.get("obstacle_mask_min_width_px", 22))
    min_height_px = int(ctrl_cfg.get("obstacle_mask_min_height_px", 16))
    min_fill_ratio = float(ctrl_cfg.get("obstacle_mask_min_fill_ratio", 0.18))

    best = None
    for label_id in range(1, int(n_labels)):
        x = int(stats[label_id, cv2.CC_STAT_LEFT])
        y = int(stats[label_id, cv2.CC_STAT_TOP])
        w = int(stats[label_id, cv2.CC_STAT_WIDTH])
        h = int(stats[label_id, cv2.CC_STAT_HEIGHT])
        area = int(stats[label_id, cv2.CC_STAT_AREA])
        if area < min_component_pixels or w < min_width_px or h < min_height_px:
            continue
        fill_ratio = float(area) / float(max(1, w * h))
        if fill_ratio < min_fill_ratio:
            continue
        if best is None or area > best["area"]:
            best = {"x": x, "y": y, "w": w, "h": h, "area": area}

    if best is None:
        return None

    frame_area = float(max(1, width * height))
    area_ratio = float(best["area"]) / frame_area
    min_area_ratio = float(ctrl_cfg.get("obstacle_mask_min_area_ratio", ctrl_cfg.get("obstacle_min_area_ratio", 0.015)))
    emergency_area_ratio = float(
        ctrl_cfg.get("obstacle_mask_emergency_area_ratio", ctrl_cfg.get("obstacle_emergency_area_ratio", 0.06))
    )
    if area_ratio < min_area_ratio:
        return None

    cx = float(best["x"] + (best["w"] / 2.0))
    roi_left = int(float(ctrl_cfg.get("obstacle_roi_left_ratio", 0.2)) * width)
    roi_right = int(float(ctrl_cfg.get("obstacle_roi_right_ratio", 0.8)) * width)
    if not (roi_left <= cx <= roi_right):
        return None

    area_span = max(1e-6, emergency_area_ratio - min_area_ratio)
    urgency = _clamp((area_ratio - min_area_ratio) / area_span, 0.0, 1.0)
    return {
        "label": "box_mask",
        "score": 1.0,
        "area_ratio": area_ratio,
        "box": [
            int(best["x"]),
            int(best["y"] + roi_top),
            int(best["x"] + best["w"]),
            int(best["y"] + roi_top + best["h"]),
        ],
        "emergency": area_ratio >= emergency_area_ratio,
        "urgency": float(urgency),
        "cx": cx,
        "source": "box_mask",
    }


def _choose_avoid_direction(lane_info, frame_shape, obstacle, previous_direction):
    _, width = frame_shape[:2]
    frame_center_x = float(width) / 2.0
    cx = obstacle.get("cx")
    if cx is not None:
        delta = float(cx) - frame_center_x
        if abs(delta) > (0.06 * width):
            # Obstacle on left -> steer right (+1), obstacle on right -> steer left (-1)
            return 1.0 if delta < 0 else -1.0

    track_mask = lane_info.get("track_mask")
    if track_mask is not None:
        mid = width // 2
        left_score = int(np.count_nonzero(track_mask[:, :mid]))
        right_score = int(np.count_nonzero(track_mask[:, mid:]))
        if left_score > right_score:
            return -1.0
        if right_score > left_score:
            return 1.0

    if previous_direction is not None:
        return 1.0 if float(previous_direction) >= 0 else -1.0
    return 1.0


def compute_autonomy_command(lane_info, frame_shape, ctrl_cfg, detections=None, runtime_state=None):
    if runtime_state is None:
        runtime_state = {}

    _, width = frame_shape[:2]
    frame_half = max(width / 2.0, 1.0)
    offset_px = lane_info.get("center_offset_px")
    base_throttle = float(ctrl_cfg.get("auto_forward_throttle", 0.18))
    max_throttle = float(ctrl_cfg.get("auto_forward_throttle_max", base_throttle))
    max_steering = float(ctrl_cfg.get("auto_max_steering", 0.65))

    det_obstacle = _obstacle_risk(frame_shape, detections or [], ctrl_cfg)
    mask_obstacle = _box_mask_obstacle_risk(frame_shape, lane_info, ctrl_cfg)
    if det_obstacle is None:
        obstacle = mask_obstacle
    elif mask_obstacle is None:
        obstacle = det_obstacle
    else:
        obstacle = det_obstacle if float(det_obstacle.get("urgency", 0.0)) >= float(mask_obstacle.get("urgency", 0.0)) else mask_obstacle

    now = time.monotonic()
    if obstacle is not None:
        if obstacle["emergency"]:
            runtime_state["obstacle_avoid_until"] = 0.0
            mode = "obstacle_stop"
            throttle = 0.0
        else:
            prev_dir = runtime_state.get("obstacle_avoid_direction")
            avoid_dir = _choose_avoid_direction(lane_info, frame_shape, obstacle, prev_dir)
            runtime_state["obstacle_avoid_direction"] = avoid_dir
            runtime_state["obstacle_avoid_until"] = now + float(ctrl_cfg.get("obstacle_avoid_hold_sec", 0.45))

            lane_steer = _lane_steering_from_offset(offset_px, frame_half, ctrl_cfg, max_steering)
            urgency = float(obstacle.get("urgency", 0.0))
            avoid_min = float(ctrl_cfg.get("obstacle_avoid_steering_min", 0.25))
            avoid_max = float(ctrl_cfg.get("obstacle_avoid_steering_max", 0.75))
            avoid_mag = _clamp(avoid_min + (avoid_max - avoid_min) * urgency, 0.0, max_steering)
            lane_blend = float(ctrl_cfg.get("obstacle_avoid_lane_blend", 0.35))

            mode = "obstacle_avoid"
            steering = _clamp((avoid_dir * avoid_mag) + (lane_steer * lane_blend), -max_steering, max_steering)
            slowdown_gain = float(ctrl_cfg.get("obstacle_avoid_slowdown_gain", 0.85))
            min_caution_throttle = float(ctrl_cfg.get("obstacle_preempt_min_throttle", 0.12))
            throttle_scale = _clamp(1.0 - (slowdown_gain * urgency), 0.0, 1.0)
            throttle = max(min_caution_throttle, base_throttle * throttle_scale)
            return {
                "mode": mode,
                "reason": f"{mode}:{obstacle['label']}:{obstacle['score']:.2f}:{obstacle.get('source', 'det')}",
                "steering": float(steering),
                "throttle": float(_clamp(throttle, 0.0, max_throttle)),
                "offset_px": None if offset_px is None else float(offset_px),
                "offset_norm": None if offset_px is None else float(offset_px / frame_half),
                "obstacle": obstacle,
            }

    avoid_until = float(runtime_state.get("obstacle_avoid_until", 0.0) or 0.0)
    avoid_dir = runtime_state.get("obstacle_avoid_direction")
    if (now < avoid_until) and (not lane_info.get("has_center")) and (avoid_dir is not None):
        hold_steering = float(ctrl_cfg.get("obstacle_hold_steering", 0.22))
        hold_throttle_scale = float(ctrl_cfg.get("obstacle_hold_throttle_scale", 0.65))
        steering = float(_clamp(float(avoid_dir) * hold_steering, -max_steering, max_steering))
        throttle = float(_clamp(base_throttle * hold_throttle_scale, 0.0, max_throttle))
        return {
            "mode": "obstacle_hold",
            "reason": "obstacle_hold_lane_reacquire",
            "steering": steering,
            "throttle": throttle,
            "offset_px": None if offset_px is None else float(offset_px),
            "offset_norm": None if offset_px is None else float(offset_px / frame_half),
        }

    if not lane_info.get("has_center"):
        lane_lost_policy = str(ctrl_cfg.get("auto_lane_lost_policy", "stop")).lower()
        if lane_lost_policy == "stop":
            return {
                "mode": "stop",
                "reason": "lane_lost_stop",
                "steering": 0.0,
                "throttle": 0.0,
                "offset_px": None,
                "offset_norm": None,
            }
        last_offset_px = lane_info.get("last_offset_px")
        if last_offset_px is not None:
            offset_norm = float(last_offset_px / frame_half)
            steering_decay = float(ctrl_cfg.get("auto_lane_lost_steering_decay", 0.8))
            throttle_scale = float(ctrl_cfg.get("auto_lane_lost_throttle_scale", 0.65))
            steering = _clamp(offset_norm * float(ctrl_cfg.get("auto_steering_kp", 0.9)) * steering_decay, -max_steering, max_steering)
            throttle = _clamp(base_throttle * throttle_scale, 0.0, max_throttle)
            return {
                "mode": "lane_search",
                "reason": "lane_lost_keep_moving",
                "steering": float(steering),
                "throttle": float(throttle),
                "offset_px": float(last_offset_px),
                "offset_norm": float(offset_norm),
            }
        return {
            "mode": "lane_search",
            "reason": "lane_lost_forward",
            "steering": 0.0,
            "throttle": float(_clamp(base_throttle * float(ctrl_cfg.get("auto_lane_lost_throttle_scale", 0.65)), 0.0, max_throttle)),
            "offset_px": None,
            "offset_norm": None,
            }

    offset_norm = float(offset_px / frame_half)
    min_scale = float(ctrl_cfg.get("auto_min_throttle_scale", 0.45))
    steering_scale = float(ctrl_cfg.get("auto_throttle_steering_scale", 0.8))
    single_boundary_scale = float(ctrl_cfg.get("auto_single_boundary_throttle_scale", 0.75))

    steering = _lane_steering_from_offset(offset_px, frame_half, ctrl_cfg, max_steering)
    throttle_scale = max(min_scale, 1.0 - (steering_scale * abs(steering)))
    if lane_info.get("source") != "dual_boundary":
        throttle_scale *= single_boundary_scale

    throttle = base_throttle * throttle_scale
    throttle = _clamp(throttle, 0.0, max_throttle)

    return {
        "mode": "lane_follow",
        "reason": lane_info.get("source", "lane_follow"),
        "steering": float(steering),
        "throttle": float(throttle),
        "offset_px": float(offset_px),
        "offset_norm": float(offset_norm),
    }
