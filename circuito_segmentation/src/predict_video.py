import argparse
from pathlib import Path

import cv2

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
    parser.add_argument("--source", default="0")
    parser.add_argument("--out", default=None)
    parser.add_argument("--threshold", type=float, default=0.5)
    parser.add_argument("--cpu", action="store_true")
    return parser.parse_args()


def open_source(source):
    if str(source).isdigit():
        return cv2.VideoCapture(int(source))
    return cv2.VideoCapture(source)


def main():
    args = parse_args()
    device = get_device(force_cpu=args.cpu)
    model, img_size, _ = load_model(args.checkpoint, device)
    cap = open_source(args.source)
    if not cap.isOpened():
        raise RuntimeError(f"No pude abrir la fuente de video: {args.source}")

    writer = None
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        fps = cap.get(cv2.CAP_PROP_FPS) or 20.0
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(str(out_path), fourcc, fps, (width, height))

    while True:
        ok, frame = cap.read()
        if not ok:
            break

        masks = predict_masks(model, frame, img_size, device, threshold=args.threshold)
        track_mask = masks[0]
        obstacle_mask = masks[1] if len(masks) > 1 else track_mask * 0
        error, confidence = compute_steering_error(track_mask)
        obstacle_error, obstacle_confidence = compute_obstacle_error(obstacle_mask)
        view = overlay_masks(frame, track_mask, obstacle_mask)

        text = "sin linea"
        if error is not None:
            text = f"track={error:+.2f} conf={confidence:.2f}"
        if obstacle_error is not None:
            text += f" obs={obstacle_error:+.2f}/{obstacle_confidence:.2f}"
        cv2.putText(
            view,
            text,
            (20, 35),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 255, 255),
            2,
            cv2.LINE_AA,
        )

        if writer:
            writer.write(view)
        else:
            cv2.imshow("segmentacion circuito", view)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

    cap.release()
    if writer:
        writer.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
