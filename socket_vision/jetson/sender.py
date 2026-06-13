import argparse
import socket
import time
from pathlib import Path

import cv2

from socket_vision.config_loader import load_runtime_config
from socket_vision.conexion.protocol import send_frame, send_frame_udp


def now_ns() -> int:
    return int(time.time() * 1e9)


def open_camera(cfg_stream):
    w = int(cfg_stream["width"])
    h = int(cfg_stream["height"])
    fps = int(cfg_stream["fps"])

    if bool(cfg_stream.get("use_gstreamer", False)):
        pipeline = str(cfg_stream["gstreamer_pipeline"])
        # Keep only the latest frame to minimize end-to-end latency.
        if "appsink" in pipeline and "drop=true" not in pipeline:
            pipeline = pipeline.replace("appsink", "appsink drop=true max-buffers=1 sync=false")
        cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
    else:
        cap = cv2.VideoCapture(int(cfg_stream.get("camera_index", 0)))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
        cap.set(cv2.CAP_PROP_FPS, fps)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    if not cap.isOpened():
        raise RuntimeError("Could not open camera")
    return cap


def main():
    parser = argparse.ArgumentParser(description="Jetson socket video sender")
    parser.add_argument("--config", default=None, help="Legacy single config file")
    parser.add_argument("--config-dir", default="socket_vision")
    args = parser.parse_args()

    cfg = load_runtime_config(config_path=args.config, config_dir=args.config_dir)
    net = cfg["network"]
    stream = cfg["stream"]

    dst_ip = net.get("receiver_ip", net["jetson_ip"])
    port = int(net["port"])
    timeout = float(net["socket_timeout_sec"])
    reconnect = float(net["reconnect_delay_sec"])
    video_transport = str(net.get("video_transport", "tcp")).lower()
    udp_payload_bytes = int(net.get("udp_payload_bytes", 1200))
    quality = int(stream["jpeg_quality"])

    print(f"[sender] target {dst_ip}:{port}")
    cap = open_camera(stream)
    frame_count = 0
    t0 = time.perf_counter()

    if video_transport == "udp":
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        frame_id = 0
        print(f"[sender] UDP mode target {dst_ip}:{port} payload={udp_payload_bytes}B")
        try:
            while True:
                ok, frame = cap.read()
                if not ok:
                    print("[sender] frame capture failed")
                    time.sleep(0.05)
                    continue
                ok, enc = cv2.imencode(
                    ".jpg",
                    frame,
                    [int(cv2.IMWRITE_JPEG_QUALITY), quality],
                )
                if not ok:
                    continue
                ts_ns = now_ns()
                send_frame_udp(
                    sock,
                    (dst_ip, port),
                    enc.tobytes(),
                    ts_ns,
                    frame_id,
                    max_datagram_bytes=udp_payload_bytes,
                )
                frame_id = (frame_id + 1) & 0xFFFFFFFF
                frame_count += 1
                if frame_count % 60 == 0:
                    dt = max(time.perf_counter() - t0, 1e-6)
                    fps = frame_count / dt
                    print(f"[sender] frames={frame_count} avg_fps={fps:.1f}")
        except KeyboardInterrupt:
            print("[sender] interrupted by user")
        finally:
            sock.close()
            cap.release()
        return

    while True:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

        try:
            print("[sender] connecting...")
            sock.connect((dst_ip, port))
            print("[sender] connected")

            while True:
                ok, frame = cap.read()
                if not ok:
                    print("[sender] frame capture failed")
                    time.sleep(0.05)
                    continue

                ok, enc = cv2.imencode(
                    ".jpg",
                    frame,
                    [int(cv2.IMWRITE_JPEG_QUALITY), quality],
                )
                if not ok:
                    continue

                ts_ns = now_ns()
                send_frame(sock, enc.tobytes(), ts_ns)
                frame_count += 1
                if frame_count % 60 == 0:
                    dt = max(time.perf_counter() - t0, 1e-6)
                    fps = frame_count / dt
                    print(f"[sender] frames={frame_count} avg_fps={fps:.1f}")

        except (ConnectionRefusedError, socket.timeout, ConnectionError, OSError) as e:
            print(f"[sender] disconnected: {e}")
            time.sleep(reconnect)
        except KeyboardInterrupt:
            print("[sender] interrupted by user")
            break
        finally:
            sock.close()
    cap.release()


if __name__ == "__main__":
    main()
