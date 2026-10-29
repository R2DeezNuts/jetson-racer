import cv2
import numpy as np


def draw_overlay(frame, lane_contours, lane_info, latency_ms, fps, control_state, cfg, detections=None):
    vis = frame.copy()
    t = int(cfg["draw_edge_thickness"])
    height, width = frame.shape[:2]

    # Raw model masks overlay (single main window): track in green, box in red.
    track_mask = lane_info.get("track_mask")
    if track_mask is not None:
        vis[track_mask > 0] = (0, 255, 0)
    box_mask = lane_info.get("box_mask")
    if box_mask is not None:
        vis[box_mask > 0] = (0, 0, 255)
    if track_mask is not None or box_mask is not None:
        vis = cv2.addWeighted(frame, 0.72, vis, 0.28, 0.0)

    if lane_contours:
        cv2.drawContours(vis, lane_contours, -1, (255, 220, 0), t)

    if lane_info["left_boundary_x"] is not None:
        x = int(lane_info["left_boundary_x"])
        cv2.line(vis, (x, lane_info["roi_start_y"]), (x, height - 1), (0, 220, 255), 2)
    if lane_info["right_boundary_x"] is not None:
        x = int(lane_info["right_boundary_x"])
        cv2.line(vis, (x, lane_info["roi_start_y"]), (x, height - 1), (0, 220, 255), 2)

    if lane_info["has_center"]:
        x = int(lane_info["lane_center_x"])
        cv2.line(vis, (x, lane_info["roi_start_y"]), (x, height - 1), (80, 255, 80), 2)

    tape_points = lane_info.get("tape_points") or []
    if len(tape_points) >= 2:
        pts = np.array([(int(x), int(y)) for x, y in tape_points], dtype=np.int32).reshape(-1, 1, 2)
        cv2.polylines(vis, [pts], False, (80, 255, 220), 2)

    frame_center_x = int(width / 2)
    cv2.line(vis, (frame_center_x, lane_info["roi_start_y"]), (frame_center_x, height - 1), (255, 80, 80), 1)

    status = f"FPS:{fps:.1f} Lat:{latency_ms:.1f}ms Lane:{lane_info['source']}"
    cv2.putText(
        vis,
        status,
        (10, 24),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )

    if detections:
        for det in detections:
            x1, y1, x2, y2 = det["box"]
            score = float(det.get("score", 0.0))
            label = str(det.get("label", "obj"))
            cv2.rectangle(vis, (x1, y1), (x2, y2), (40, 40, 255), 2)
            cv2.putText(
                vis,
                f"{label}:{score:.2f}",
                (x1, max(16, y1 - 6)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (40, 40, 255),
                2,
                cv2.LINE_AA,
            )

    if control_state is not None:
        offset_px = control_state.get("offset_px")
        offset_text = "n/a" if offset_px is None else f"{offset_px:+.1f}px"
        cv2.putText(
            vis,
            (
                f"Auto:{control_state.get('mode', 'off')} "
                f"Steer:{control_state.get('steering', 0.0):+.2f} "
                f"Thr:{control_state.get('throttle', 0.0):+.2f} "
                f"Offset:{offset_text}"
            ),
            (10, 50),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )
        cv2.putText(
            vis,
            control_state.get("reason", ""),
            (10, 74),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )

    return vis
