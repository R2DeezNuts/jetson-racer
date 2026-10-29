import argparse
from pathlib import Path

import torch
import torch.optim as optim
from torch.utils.data import DataLoader
from tqdm import tqdm

from dataset import CircuitDataset
from losses import DiceBCELoss, channel_metrics_from_logits, dice_score_from_logits, iou_from_logits
from model import build_model
from utils import get_device, save_checkpoint


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--epochs", type=int, default=40)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--img-size", type=int, default=256)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--base-channels", type=int, default=32)
    parser.add_argument("--obstacle-weight", type=float, default=2.0)
    parser.add_argument("--num-workers", type=int, default=2)
    parser.add_argument("--checkpoint-dir", default="checkpoints")
    parser.add_argument("--cpu", action="store_true")
    return parser.parse_args()


def run_epoch(model, loader, loss_fn, device, optimizer=None):
    training = optimizer is not None
    model.train(training)
    total_loss = 0.0
    total_dice = 0.0
    total_iou = 0.0

    progress = tqdm(loader, leave=False)
    for images, masks in progress:
        images = images.to(device)
        masks = masks.to(device)

        if training:
            optimizer.zero_grad(set_to_none=True)

        with torch.set_grad_enabled(training):
            logits = model(images)
            loss = loss_fn(logits, masks)
            if training:
                loss.backward()
                optimizer.step()

        dice = dice_score_from_logits(logits, masks)
        iou = iou_from_logits(logits, masks)
        channel_metrics = channel_metrics_from_logits(logits, masks)
        total_loss += loss.item()
        total_dice += dice.item()
        total_iou += iou.item()
        progress.set_postfix(
            loss=loss.item(),
            dice=dice.item(),
            iou=iou.item(),
            obs=channel_metrics.get("obstacle_dice", 0.0),
        )

    n = max(1, len(loader))
    return total_loss / n, total_dice / n, total_iou / n


def main():
    args = parse_args()
    device = get_device(force_cpu=args.cpu)
    data_dir = Path(args.data_dir)

    train_ds = CircuitDataset(
        data_dir / "train" / "images",
        data_dir / "train" / "track_masks",
        data_dir / "train" / "obstacle_masks",
        img_size=args.img_size,
    )
    val_ds = CircuitDataset(
        data_dir / "val" / "images",
        data_dir / "val" / "track_masks",
        data_dir / "val" / "obstacle_masks",
        img_size=args.img_size,
    )

    train_loader = DataLoader(
        train_ds,
        batch_size=args.batch_size,
        shuffle=True,
        num_workers=args.num_workers,
        pin_memory=device.type == "cuda",
    )
    val_loader = DataLoader(
        val_ds,
        batch_size=args.batch_size,
        shuffle=False,
        num_workers=args.num_workers,
        pin_memory=device.type == "cuda",
    )

    out_channels = 2
    model = build_model(base_channels=args.base_channels, out_channels=out_channels).to(device)
    loss_fn = DiceBCELoss(obstacle_weight=args.obstacle_weight)
    optimizer = optim.Adam(model.parameters(), lr=args.lr)
    best_dice = -1.0
    checkpoint_dir = Path(args.checkpoint_dir)

    print(f"Device: {device}")
    print(f"Train: {len(train_ds)} imagenes | Val: {len(val_ds)} imagenes")

    for epoch in range(1, args.epochs + 1):
        print(f"\nEpoch {epoch}/{args.epochs}")
        train_loss, train_dice, train_iou = run_epoch(
            model, train_loader, loss_fn, device, optimizer=optimizer
        )
        val_loss, val_dice, val_iou = run_epoch(model, val_loader, loss_fn, device)

        print(
            "train "
            f"loss={train_loss:.4f} dice={train_dice:.4f} iou={train_iou:.4f} | "
            "val "
            f"loss={val_loss:.4f} dice={val_dice:.4f} iou={val_iou:.4f}"
        )

        save_checkpoint(
            checkpoint_dir / "last_model.pth",
            model,
            optimizer,
            epoch,
            args.img_size,
            args.base_channels,
            out_channels,
            best_dice,
        )

        if val_dice > best_dice:
            best_dice = val_dice
            save_checkpoint(
                checkpoint_dir / "best_model.pth",
                model,
                optimizer,
                epoch,
                args.img_size,
                args.base_channels,
                out_channels,
                best_dice,
            )
            print(f"Nuevo mejor modelo guardado: dice={best_dice:.4f}")


if __name__ == "__main__":
    main()
