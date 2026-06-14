"""Crop a face bounding box from a photo and cache the result."""
import os
from pathlib import Path
from typing import Optional

_CACHE = Path(os.getenv("CACHE_PATH", "/cache")) / "face_crops"
try:
    _CACHE.mkdir(parents=True, exist_ok=True)
except PermissionError:
    _CACHE = Path("/tmp/photoflow-face-crops")
    _CACHE.mkdir(parents=True, exist_ok=True)


def crop_face(photo_path: str, bbox: list, person_id: int, face_id: int, size: int = 160) -> Optional[str]:
    """Crop face from photo and save as JPEG. Returns path or None on error."""
    out = _CACHE / f"p{person_id}_f{face_id}.jpg"
    if out.exists():
        return str(out)

    try:
        from PIL import Image
        img = Image.open(photo_path)
        if img.mode != "RGB":
            img = img.convert("RGB")

        w, h = img.size
        x1, y1, x2, y2 = bbox[0], bbox[1], bbox[2], bbox[3]

        # bbox may be normalized [0-1] or pixel coords — detect
        if all(0 <= v <= 1 for v in [x1, y1, x2, y2]):
            x1, y1, x2, y2 = int(x1 * w), int(y1 * h), int(x2 * w), int(y2 * h)

        # Expand box by 30% for context
        pad_x = int((x2 - x1) * 0.3)
        pad_y = int((y2 - y1) * 0.3)
        x1 = max(0, x1 - pad_x)
        y1 = max(0, y1 - pad_y)
        x2 = min(w, x2 + pad_x)
        y2 = min(h, y2 + pad_y)

        crop = img.crop((x1, y1, x2, y2))
        crop.thumbnail((size, size), Image.LANCZOS)

        # Square-pad
        sq = Image.new("RGB", (size, size), (200, 200, 200))
        ox = (size - crop.width) // 2
        oy = (size - crop.height) // 2
        sq.paste(crop, (ox, oy))
        sq.save(str(out), "JPEG", quality=85)
        return str(out)
    except Exception:
        return None
