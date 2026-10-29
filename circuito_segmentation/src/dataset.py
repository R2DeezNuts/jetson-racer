from pathlib import Path

import numpy as np
import torch
from PIL import Image
from torch.utils.data import Dataset


IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".bmp")


class CircuitDataset(Dataset):
    def __init__(self, images_dir, track_masks_dir, obstacle_masks_dir, img_size=256):
        self.images_dir = Path(images_dir)
        self.track_masks_dir = Path(track_masks_dir)
        self.obstacle_masks_dir = Path(obstacle_masks_dir)
        self.img_size = img_size
        self.images = sorted(
            p for p in self.images_dir.iterdir() if p.suffix.lower() in IMAGE_EXTENSIONS
        )
        if not self.images:
            raise RuntimeError(f"No hay imagenes en {self.images_dir}")

    def __len__(self):
        return len(self.images)

    def __getitem__(self, index):
        image_path = self.images[index]
        track_mask_path = self._find_mask(image_path, self.track_masks_dir, "circuito")
        obstacle_mask_path = self._find_mask(image_path, self.obstacle_masks_dir, "obstaculo")

        image = Image.open(image_path).convert("RGB")
        track_mask = Image.open(track_mask_path).convert("L")
        obstacle_mask = Image.open(obstacle_mask_path).convert("L")

        image = image.resize((self.img_size, self.img_size), Image.BILINEAR)
        track_mask = track_mask.resize((self.img_size, self.img_size), Image.NEAREST)
        obstacle_mask = obstacle_mask.resize((self.img_size, self.img_size), Image.NEAREST)

        image_np = np.asarray(image, dtype=np.float32) / 255.0
        track_np = np.asarray(track_mask, dtype=np.float32)
        obstacle_np = np.asarray(obstacle_mask, dtype=np.float32)
        track_np = (track_np > 127).astype(np.float32)
        obstacle_np = (obstacle_np > 127).astype(np.float32)

        image_tensor = torch.from_numpy(image_np).permute(2, 0, 1)
        mask_tensor = torch.from_numpy(np.stack([track_np, obstacle_np], axis=0))
        return image_tensor, mask_tensor

    @staticmethod
    def _find_mask(image_path, masks_dir, label):
        for ext in IMAGE_EXTENSIONS:
            candidate = masks_dir / f"{image_path.stem}{ext}"
            if candidate.exists():
                return candidate
        raise FileNotFoundError(
            f"No encontre mascara de {label} para {image_path.name} en {masks_dir}. "
            "Debe tener el mismo nombre base."
        )
