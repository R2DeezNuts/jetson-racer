import argparse
from pathlib import Path

import torch

from utils import get_device, load_model


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--out", default="exports/circuit_unet.onnx")
    parser.add_argument("--cpu", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    device = get_device(force_cpu=args.cpu)
    model, img_size, _ = load_model(args.checkpoint, device)
    dummy = torch.randn(1, 3, img_size, img_size, device=device)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    torch.onnx.export(
        model,
        dummy,
        str(out_path),
        input_names=["image"],
        output_names=["logits"],
        opset_version=12,
        dynamic_axes=None,
    )
    print(f"ONNX guardado en: {out_path}")


if __name__ == "__main__":
    main()

