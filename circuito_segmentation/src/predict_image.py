import argparse
from pathlib import Path

import cv2

from utils import get_device, load_model, overlay_masks, predict_masks


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--out", default="outputs/prediccion.png")
    parser.add_argument("--threshold", type=float, default=0.5)
    parser.add_argument("--cpu", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    device = get_device(force_cpu=args.cpu)
    model, img_size, _ = load_model(args.checkpoint, device)

    frame = cv2.imread(args.image)
    if frame is None:
        raise RuntimeError(f"No pude leer la imagen: {args.image}")

    masks = predict_masks(model, frame, img_size, device, threshold=args.threshold)
    track_mask = masks[0]
    obstacle_mask = masks[1] if len(masks) > 1 else track_mask * 0
    overlay = overlay_masks(frame, track_mask, obstacle_mask)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out_path), overlay)
    cv2.imwrite(str(out_path.with_name(out_path.stem + "_track_mask.png")), track_mask)
    cv2.imwrite(str(out_path.with_name(out_path.stem + "_obstacle_mask.png")), obstacle_mask)
    print(f"Guardado: {out_path}")


if __name__ == "__main__":
    main()
