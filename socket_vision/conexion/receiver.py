import argparse
import select
import socket
import time
from collections import deque
from pathlib import Path

import cv2
import numpy as np

from socket_vision.config_loader import load_runtime_config
from socket_vision.conexion.protocol import UdpFrameAssembler, recv_frame
from socket_vision.control.protocol import recv_json_line, send_json_line
from socket_vision.vision.runtime.autonomy import compute_autonomy_command
from socket_vision.vision.runtime.vision import draw_overlay
from socket_vision.vision.perception.pipeline import create_perception


def recv_frame_udp_latest(sock: socket.socket, assembler: UdpFrameAssembler, timeout: float):
    deadline = time.monotonic() + max(timeout, 0.05)
    latest = assembler.pop_latest_complete()
    if latest is not None:
        return latest
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise socket.timeout("udp frame timeout")
        sock.settimeout(remaining)
        packet, _ = sock.recvfrom(65535)
        complete = assembler.feed_packet(packet)
        if complete is None:
            continue
        latest = complete
        # Drain queued datagrams and keep newest complete frame only.
        while True:
            ready, _, _ = select.select([sock], [], [], 0.0)
            if not ready:
                break
            packet, _ = sock.recvfrom(65535)
            complete = assembler.feed_packet(packet)
            if complete is not None:
                latest = complete
        return latest


def smooth_lane_info(lane_info, prev_offset_px, ctrl_cfg, frame_width):
    if not lane_info.get("has_center"):
        lane_info = dict(lane_info)
        lane_info["last_offset_px"] = prev_offset_px
        return lane_info, prev_offset_px

    alpha = float(ctrl_cfg.get("auto_offset_ema_alpha", 0.35))
    alpha = max(0.0, min(alpha, 1.0))
    raw_offset_px = float(lane_info["center_offset_px"])
    if prev_offset_px is None:
        smoothed_offset_px = raw_offset_px
    else:
        smoothed_offset_px = (alpha * raw_offset_px) + ((1.0 - alpha) * prev_offset_px)

    lane_info = dict(lane_info)
    lane_info["raw_center_offset_px"] = raw_offset_px
    lane_info["center_offset_px"] = smoothed_offset_px
    lane_info["last_offset_px"] = smoothed_offset_px
    lane_info["lane_center_x"] = lane_info["frame_center_x"] + smoothed_offset_px
    lane_info["left_boundary_x_raw"] = lane_info.get("left_boundary_x")
    lane_info["right_boundary_x_raw"] = lane_info.get("right_boundary_x")
    lane_info["lane_center_x"] = max(0.0, min(float(frame_width - 1), float(lane_info["lane_center_x"])))
    return lane_info, smoothed_offset_px


class ControlLink:
    def __init__(self, cfg):
        ctrl_cfg = cfg["control"]
        net_cfg = cfg["network"]
        self.enabled = bool(ctrl_cfg.get("autonomy_enabled", True))
        self.host = net_cfg.get("jetson_control_ip", "192.168.1.43")
        self.port = int(ctrl_cfg.get("port", 5060))
        self.timeout = float(ctrl_cfg.get("socket_timeout_sec", 4))
        self.sock = None
        self.last_error = 0.0

    def close(self):
        if self.sock is not None:
            try:
                self.sock.close()
            except OSError:
                pass
            self.sock = None

    def stop_vehicle(self):
        if not self.enabled:
            return
        payload = {
            "cmd": "stop",
            "source": "auto",
            "reason": "receiver_shutdown",
            "mode": "stop",
        }
        try:
            self._connect()
            send_json_line(self.sock, payload)
            _ = recv_json_line(self.sock)
            print("[receiver] stop command sent to control server")
        except (ConnectionError, OSError, socket.timeout) as exc:
            print(f"[receiver] failed to send stop command: {exc}")

    def _connect(self):
        if not self.enabled or self.sock is not None:
            return
        self.sock = socket.create_connection((self.host, self.port), timeout=2.5)
        self.sock.settimeout(self.timeout)
        print(f"[receiver] auto-control connected to {self.host}:{self.port}")

    def send_auto(self, control_state):
        if not self.enabled:
            return None
        payload = {
            "cmd": "auto_drive",
            "source": "auto",
            "steering": control_state["steering"],
            "throttle": control_state["throttle"],
            "reason": control_state["reason"],
            "mode": control_state["mode"],
        }
        try:
            self._connect()
            send_json_line(self.sock, payload)
            return recv_json_line(self.sock)
        except (ConnectionError, OSError, socket.timeout) as exc:
            now = time.monotonic()
            if now - self.last_error > 1.0:
                print(f"[receiver] auto-control send failed: {exc}")
                self.last_error = now
            self.close()
            return None


def main():
    parser = argparse.ArgumentParser(description="Socket video receiver with vision")
    parser.add_argument("--config", default=None, help="Legacy single config file")
    parser.add_argument("--config-dir", default="socket_vision")
    parser.add_argument("--headless", action="store_true", help="Run without OpenCV windows")
    parser.add_argument("--disable-auto-control", action="store_true")
    args = parser.parse_args()

    cfg = load_runtime_config(config_path=args.config, config_dir=args.config_dir)
    net = cfg["network"]
    vis_cfg = cfg["vision"]
    ui_cfg = cfg["ui"]
    perception = create_perception(cfg)

    host = net["listen_ip"]
    port = int(net["port"])
    timeout = float(net["socket_timeout_sec"])
    video_transport = str(net.get("video_transport", "tcp")).lower()
    udp_max_inflight_frames = int(net.get("udp_max_inflight_frames", 8))

    control_link = ControlLink(cfg)
    if args.disable_auto_control:
        control_link.enabled = False

    win = ui_cfg["window_name"]
    show_mask = bool(ui_cfg.get("show_mask", True))
    headless = bool(args.headless)
    main_w = int(ui_cfg.get("main_window_width", 960))
    main_h = int(ui_cfg.get("main_window_height", 540))

    while True:
        if video_transport == "udp":
            server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind((host, port))
            server.settimeout(timeout)
            print(f"[receiver] UDP listening on {host}:{port} ...")
            assembler = UdpFrameAssembler(max_inflight_frames=udp_max_inflight_frames)
        else:
            server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind((host, port))
            server.listen(1)
            print(f"[receiver] listening on {host}:{port} ...")
            assembler = None

        conn = None
        try:
            if video_transport == "udp":
                conn = server
                print("[receiver] UDP stream active")
            else:
                conn, addr = server.accept()
                conn.settimeout(timeout)
                print(f"[receiver] connected from {addr}")

            last = time.perf_counter()
            fps_hist = deque(maxlen=40)
            frame_count = 0
            windows_ready = False
            smoothed_offset_px = None
            auto_runtime_state = {}
            min_raw_latency_ns = None
            last_control_state = {
                "mode": "idle",
                "reason": "waiting_frames",
                "steering": 0.0,
                "throttle": 0.0,
                "offset_px": None,
            }

            while True:
                if video_transport == "udp":
                    ts_ns, jpeg = recv_frame_udp_latest(conn, assembler, timeout)
                else:
                    ts_ns, jpeg = recv_frame(conn)
                now_ns = time.time_ns()
                latency_raw_ns = max(0, now_ns - ts_ns)
                if min_raw_latency_ns is None:
                    min_raw_latency_ns = latency_raw_ns
                else:
                    min_raw_latency_ns = min(min_raw_latency_ns, latency_raw_ns)
                # Queue latency relative to best observed baseline (robust to clock offset).
                latency_ms = max(0.0, (latency_raw_ns - min_raw_latency_ns) / 1e6)
                latency_raw_ms = max(0.0, latency_raw_ns / 1e6)

                arr = np.frombuffer(jpeg, dtype=np.uint8)
                frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                if frame is None:
                    continue

                _lane_mask, lane_contours, lane_info, detections = perception.process(frame)
                lane_info, smoothed_offset_px = smooth_lane_info(
                    lane_info,
                    smoothed_offset_px,
                    cfg["control"],
                    frame.shape[1],
                )
                control_state = compute_autonomy_command(
                    lane_info,
                    frame.shape,
                    cfg["control"],
                    detections=detections,
                    runtime_state=auto_runtime_state,
                )
                ack = control_link.send_auto(control_state)
                if ack and ack.get("applied") is False:
                    control_state["mode"] = "manual_override"
                    control_state["reason"] = ack.get("reason", "manual_override")
                last_control_state = control_state

                now = time.perf_counter()
                dt = max(now - last, 1e-6)
                last = now
                fps_hist.append(1.0 / dt)
                fps = float(sum(fps_hist) / len(fps_hist))
                frame_count += 1

                if headless:
                    if frame_count % 20 == 0:
                        offset_px = control_state["offset_px"]
                        offset_text = "n/a" if offset_px is None else f"{offset_px:+.1f}"
                        print(
                            f"[receiver] frames={frame_count} fps={fps:.1f} "
                            f"lat_ms={latency_ms:.1f} raw_ms={latency_raw_ms:.1f} lane={lane_info['source']} auto={control_state['mode']} "
                            f"offset_px={offset_text} reason={control_state['reason']} det={len(detections)}"
                        )
                else:
                    if not windows_ready:
                        cv2.namedWindow(win, cv2.WINDOW_NORMAL)
                        cv2.resizeWindow(win, main_w, main_h)
                        windows_ready = True
                    lane_info_overlay = lane_info
                    if not show_mask:
                        lane_info_overlay = dict(lane_info)
                        lane_info_overlay.pop("track_mask", None)
                        lane_info_overlay.pop("box_mask", None)
                    out = draw_overlay(
                        frame,
                        lane_contours,
                        lane_info_overlay,
                        latency_ms,
                        fps,
                        last_control_state,
                        vis_cfg,
                        detections=detections,
                    )
                    cv2.imshow(win, out)

                    key = cv2.waitKey(1) & 0xFF
                    if key in (27, ord("q")):
                        print("[receiver] exit requested")
                        control_link.stop_vehicle()
                        cv2.destroyAllWindows()
                        return

        except KeyboardInterrupt:
            print("[receiver] interrupted by user")
            control_link.stop_vehicle()
            return
        except (ConnectionError, socket.timeout, OSError) as exc:
            print(f"[receiver] connection dropped: {exc}")
            time.sleep(float(net["reconnect_delay_sec"]))
        finally:
            control_link.close()
            if conn is not None and video_transport != "udp":
                conn.close()
            server.close()
            cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
