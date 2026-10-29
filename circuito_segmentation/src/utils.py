from pathlib import Path

import cv2
import numpy as np
import torch

from model import build_model


def get_device(force_cpu=False):
    if force_cpu:
        return torch.device("cpu")
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


def save_checkpoint(path, model, optimizer, epoch, img_size, base_channels, out_channels, best_metric):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "state_dict": model.state_dict(),
            "optimizer": optimizer.state_dict() if optimizer is not None else None,
            "epoch": epoch,
            "img_size": img_size,
            "base_channels": base_channels,
            "out_channels": out_channels,
            "best_metric": best_metric,
        },
        path,
    )


def load_model(checkpoint_path, device):
    checkpoint = torch.load(checkpoint_path, map_location=device)
    base_channels = checkpoint.get("base_channels", 32)
    out_channels = checkpoint.get("out_channels", 2)
    model = build_model(base_channels=base_channels, out_channels=out_channels).to(device)
    model.load_state_dict(checkpoint["state_dict"])
    model.eval()
    img_size = checkpoint.get("img_size", 256)
    return model, img_size, checkpoint


def preprocess_bgr(frame_bgr, img_size, device):
    frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
    resized = cv2.resize(frame_rgb, (img_size, img_size), interpolation=cv2.INTER_AREA)
    tensor = torch.from_numpy(resized.astype(np.float32) / 255.0)
    tensor = tensor.permute(2, 0, 1).unsqueeze(0).to(device)
    return tensor


@torch.no_grad()
def predict_masks(model, frame_bgr, img_size, device, threshold=0.5):
    tensor = preprocess_bgr(frame_bgr, img_size, device)
    logits = model(tensor)
    probs = torch.sigmoid(logits)[0].detach().cpu().numpy()
    masks = []
    for channel in range(probs.shape[0]):
        mask_small = (probs[channel] > threshold).astype(np.uint8) * 255
        mask = cv2.resize(
            mask_small,
            (frame_bgr.shape[1], frame_bgr.shape[0]),
            interpolation=cv2.INTER_NEAREST,
        )
        masks.append(mask)
    return masks


def predict_mask(model, frame_bgr, img_size, device, threshold=0.5):
    return predict_masks(model, frame_bgr, img_size, device, threshold=threshold)[0]


def overlay_mask(frame_bgr, mask, color=(0, 255, 0), alpha=0.45):
    overlay = frame_bgr.copy()
    colored = np.zeros_like(frame_bgr)
    colored[mask > 0] = color
    return cv2.addWeighted(overlay, 1.0, colored, alpha, 0)


def overlay_masks(frame_bgr, track_mask, obstacle_mask, alpha=0.45):
    view = frame_bgr.copy()
    colored = np.zeros_like(frame_bgr)
    colored[track_mask > 0] = (0, 255, 0)
    colored[obstacle_mask > 0] = (0, 0, 255)
    return cv2.addWeighted(view, 1.0, colored, alpha, 0)


def compute_steering_error(mask, roi_y_start_ratio=0.55):
    h, w = mask.shape[:2]
    y0 = int(h * roi_y_start_ratio)
    roi = mask[y0:, :]
    ys, xs = np.where(roi > 0)
    if len(xs) < 20:
        return None, 0.0

    target_x = float(xs.mean())
    center_x = w / 2.0
    error = (target_x - center_x) / center_x
    confidence = min(1.0, len(xs) / float(roi.size * 0.15))
    return float(error), float(confidence)


def compute_obstacle_error(mask, roi_y_start_ratio=0.45):
    h, w = mask.shape[:2]
    y0 = int(h * roi_y_start_ratio)
    roi = mask[y0:, :]
    ys, xs = np.where(roi > 0)
    if len(xs) < 20:
        return None, 0.0

    obstacle_x = float(xs.mean())
    center_x = w / 2.0
    error = (obstacle_x - center_x) / center_x
    confidence = min(1.0, len(xs) / float(roi.size * 0.08))
    return float(error), float(confidence)
