import argparse
import time

import cv2
import torch

from utils import (
    compute_steering_error,
    compute_obstacle_error,
    get_device,
    load_model,
    overlay_masks,
    predict_masks,
)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--camera", default="0")
    parser.add_argument("--threshold", type=float, default=0.5)
    parser.add_argument("--kp", type=float, default=0.8)
    parser.add_argument("--base-speed", type=float, default=0.35)
    parser.add_argument("--show", action="store_true")
    parser.add_argument("--cpu", action="store_true")
    return parser.parse_args()


def open_camera(camera):
    if str(camera).isdigit():
        return cv2.VideoCapture(int(camera))
    return cv2.VideoCapture(camera)


def send_motor_command(throttle, steering):
    # TODO: Sustituir por el codigo real de tu controlador de motores/servo.
    # throttle: 0.0 parado, 1.0 maxima velocidad
    # steering: -1.0 izquierda, 0.0 recto, +1.0 derecha
    print(f"throttle={throttle:.2f} steering={steering:+.2f}")


def compute_control(track_mask, obstacle_mask, kp, base_speed):
    track_error, track_confidence = compute_steering_error(track_mask)
    obstacle_error, obstacle_confidence = compute_obstacle_error(obstacle_mask)

    if track_error is None or track_confidence < 0.05:
        return 0.0, 0.0, track_error, track_confidence, obstacle_error, obstacle_confidence

    steering = kp * track_error

    if obstacle_error is not None and obstacle_confidence > 0.08:
        # Si la caja esta a la derecha, corregimos hacia la izquierda; si esta
        # a la izquierda, corregimos hacia la derecha.
        avoid_direction = -1.0 if obstacle_error > 0 else 1.0
        avoid_strength = min(0.8, 0.25 + obstacle_confidence)
        steering += avoid_direction * avoid_strength

    steering = max(-1.0, min(1.0, steering))
    throttle = base_speed * track_confidence
    if obstacle_confidence > 0.3:
        throttle *= 0.6
    return throttle, steering, track_error, track_confidence, obstacle_error, obstacle_confidence


def main():
    args = parse_args()
    device = get_device(force_cpu=args.cpu)
    model, img_size, _ = load_model(args.checkpoint, device)

    cap = open_camera(args.camera)
    if not cap.isOpened():
        raise RuntimeError(f"No pude abrir la camara: {args.camera}")

    last = time.time()
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                send_motor_command(0.0, 0.0)
                continue

            masks = predict_masks(model, frame, img_size, device, threshold=args.threshold)
            track_mask = masks[0]
            obstacle_mask = masks[1] if len(masks) > 1 else track_mask * 0
            (
                throttle,
                steering,
                error,
                confidence,
                obstacle_error,
                obstacle_confidence,
            ) = compute_control(track_mask, obstacle_mask, args.kp, args.base_speed)

            send_motor_command(throttle, steering)

            if args.show:
                now = time.time()
                fps = 1.0 / max(1e-6, now - last)
                last = now
                view = overlay_masks(frame, track_mask, obstacle_mask)
                cv2.putText(
                    view,
                    f"trk={error if error is not None else 0:+.2f}/{confidence:.2f} "
                    f"obs={obstacle_error if obstacle_error is not None else 0:+.2f}/{obstacle_confidence:.2f} "
                    f"fps={fps:.1f}",
                    (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (0, 255, 255),
                    2,
                    cv2.LINE_AA,
                )
                cv2.imshow("jetson runtime", view)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
    finally:
        send_motor_command(0.0, 0.0)
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
