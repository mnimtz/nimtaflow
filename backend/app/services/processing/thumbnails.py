"""Generate thumbnails and cache them."""
import hashlib
from pathlib import Path
from typing import Optional, Tuple
from PIL import Image

try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:
    pass

SIZES = {
    "small": (320, 320),
    "medium": (800, 800),
    "large": (1920, 1920),
}


def _cache_path(cache_root: str, photo_path: str, size: str) -> Path:
    h = hashlib.sha256(photo_path.encode()).hexdigest()
    return Path(cache_root) / "thumbs" / size / h[:2] / f"{h}.jpg"


def generate_thumbnail(photo_path: str, cache_root: str, size: str = "medium") -> Optional[str]:
    out_path = _cache_path(cache_root, photo_path, size)
    if out_path.exists():
        return str(out_path)

    out_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        img = Image.open(photo_path)
        img.thumbnail(SIZES[size], Image.LANCZOS)

        if img.mode in ("RGBA", "P", "LA"):
            bg = Image.new("RGB", img.size, (255, 255, 255))
            bg.paste(img, mask=img.split()[-1] if img.mode in ("RGBA", "LA") else None)
            img = bg
        elif img.mode != "RGB":
            img = img.convert("RGB")

        img.save(str(out_path), "JPEG", quality=85, optimize=True)
        return str(out_path)
    except Exception:
        return None


def open_image_for_ai(photo_path: str, max_size: int = 1024) -> Optional[Image.Image]:
    try:
        img = Image.open(photo_path)
        img.thumbnail((max_size, max_size), Image.LANCZOS)
        if img.mode != "RGB":
            img = img.convert("RGB")
        return img
    except Exception:
        return None
