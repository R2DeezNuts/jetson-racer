import torch
import torch.nn as nn
import torch.nn.functional as F


class DiceBCELoss(nn.Module):
    def __init__(self, obstacle_weight=1.0):
        super().__init__()
        self.obstacle_weight = obstacle_weight

    def forward(self, logits, targets, smooth=1.0):
        bce_map = F.binary_cross_entropy_with_logits(logits, targets, reduction="none")
        weights = targets.new_ones(targets.shape)
        if targets.shape[1] > 1:
            weights[:, 1:2] = 1.0 + (self.obstacle_weight - 1.0) * targets[:, 1:2]
        bce = (bce_map * weights).mean()
        probs = torch.sigmoid(logits)
        probs = probs.reshape(-1)
        targets = targets.reshape(-1)
        intersection = (probs * targets).sum()
        dice = 1.0 - (2.0 * intersection + smooth) / (
            probs.sum() + targets.sum() + smooth
        )
        return bce + dice


def dice_score_from_logits(logits, targets, threshold=0.5, smooth=1e-8):
    probs = torch.sigmoid(logits)
    preds = (probs > threshold).float()
    preds = preds.reshape(-1)
    targets = targets.reshape(-1)
    intersection = (preds * targets).sum()
    return (2.0 * intersection + smooth) / (preds.sum() + targets.sum() + smooth)


def iou_from_logits(logits, targets, threshold=0.5, smooth=1e-8):
    probs = torch.sigmoid(logits)
    preds = (probs > threshold).float()
    preds = preds.reshape(-1)
    targets = targets.reshape(-1)
    intersection = (preds * targets).sum()
    union = preds.sum() + targets.sum() - intersection
    return (intersection + smooth) / (union + smooth)


def channel_metrics_from_logits(logits, targets, threshold=0.5, smooth=1e-8):
    probs = torch.sigmoid(logits)
    preds = (probs > threshold).float()
    metrics = {}
    names = ["track", "obstacle"]
    for channel, name in enumerate(names[: logits.shape[1]]):
        pred = preds[:, channel].reshape(-1)
        target = targets[:, channel].reshape(-1)
        intersection = (pred * target).sum()
        union = pred.sum() + target.sum() - intersection
        dice = (2.0 * intersection + smooth) / (pred.sum() + target.sum() + smooth)
        iou = (intersection + smooth) / (union + smooth)
        metrics[f"{name}_dice"] = dice.item()
        metrics[f"{name}_iou"] = iou.item()
    return metrics
