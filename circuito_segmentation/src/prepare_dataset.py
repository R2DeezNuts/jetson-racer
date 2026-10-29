import argparse
import random
import shutil
from pathlib import Path


IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".bmp")


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", default="raw")
    parser.add_argument("--out-dir", default="data")
    parser.add_argument("--val-size", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--copy", action="store_true", help="Copia archivos en vez de crear enlaces.")
    return parser.parse_args()


def split_items(items, val_size, seed):
    try:
        from sklearn.model_selection import train_test_split

        return train_test_split(items, test_size=val_size, random_state=seed, shuffle=True)
    except ImportError:
        rng = random.Random(seed)
        items = list(items)
        rng.shuffle(items)
        val_count = max(1, int(round(len(items) * val_size)))
        return items[val_count:], items[:val_count]


def find_mask(mask_dir, image_path):
    for ext in IMAGE_EXTENSIONS:
        candidate = mask_dir / f"{image_path.stem}{ext}"
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"No encontre mascara para {image_path.name} en {mask_dir}")


def link_or_copy(src, dst, copy):
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists() or dst.is_symlink():
        dst.unlink()
    if copy:
        shutil.copy2(src, dst)
    else:
        dst.symlink_to(src.resolve())


def write_split(split_name, images, raw_dir, out_dir, copy):
    for image_path in images:
        track_mask = find_mask(raw_dir / "track_masks", image_path)
        obstacle_mask = find_mask(raw_dir / "obstacle_masks", image_path)

        link_or_copy(image_path, out_dir / split_name / "images" / image_path.name, copy)
        link_or_copy(
            track_mask,
            out_dir / split_name / "track_masks" / f"{image_path.stem}{track_mask.suffix}",
            copy,
        )
        link_or_copy(
            obstacle_mask,
            out_dir / split_name / "obstacle_masks" / f"{image_path.stem}{obstacle_mask.suffix}",
            copy,
        )


def main():
    args = parse_args()
    raw_dir = Path(args.raw_dir)
    out_dir = Path(args.out_dir)
    images_dir = raw_dir / "images"

    images = sorted(p for p in images_dir.iterdir() if p.suffix.lower() in IMAGE_EXTENSIONS)
    if len(images) < 2:
        raise RuntimeError(f"Necesitas al menos 2 imagenes en {images_dir}")

    for image_path in images:
        find_mask(raw_dir / "track_masks", image_path)
        find_mask(raw_dir / "obstacle_masks", image_path)

    train_images, val_images = split_items(images, args.val_size, args.seed)

    write_split("train", train_images, raw_dir, out_dir, args.copy)
    write_split("val", val_images, raw_dir, out_dir, args.copy)

    print(f"Dataset preparado en {out_dir}")
    print(f"Train: {len(train_images)} imagenes")
    print(f"Val: {len(val_images)} imagenes")
    if not args.copy:
        print("Se han creado enlaces simbolicos. Usa --copy si prefieres copias reales.")


if __name__ == "__main__":
    main()
