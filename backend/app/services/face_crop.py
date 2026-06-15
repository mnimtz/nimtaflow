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


def crop_face(photo_path: str, bbox: list, person_id: int, face_id: int, size: int = 256) -> Optional[str]:
    """Crop face from photo and save as JPEG. Returns path or None on error."""
    # _v2: square crops now fill the frame (ImageOps.fit) instead of grey-padding,
    # so circular avatars show only face pixels. New suffix forces a regen of any
    # old letterboxed crops.
    out = _CACHE / f"p{person_id}_f{face_id}_v2.jpg"
    if out.exists():
        return str(out)

    try:
        from PIL import Image
        from app.services.processing.thumbnails import _open_image_any
        img = _open_image_any(photo_path)  # HEIC/MOV-safe (ffmpeg/exiftool fallback)
        if img is None:
            return None
        try:
            from PIL import ImageOps
            img = ImageOps.exif_transpose(img)  # respect orientation
        except Exception:
            pass
        if img.mode != "RGB":
            img = img.convert("RGB")

        w, h = img.size
        # Face stores bbox as [x, y, width, height] (relative 0-1 or pixels)
        bx, by, bw, bh = bbox[0], bbox[1], bbox[2], bbox[3]
        x1, y1, x2, y2 = bx, by, bx + bw, by + bh
        if all(0 <= v <= 1 for v in [bx, by, bw, bh]):
            x1, y1, x2, y2 = int(x1 * w), int(y1 * h), int(x2 * w), int(y2 * h)

        # Expand box by 30% for context
        pad_x = int((x2 - x1) * 0.3)
        pad_y = int((y2 - y1) * 0.3)
        x1 = max(0, x1 - pad_x)
        y1 = max(0, y1 - pad_y)
        x2 = min(w, x2 + pad_x)
        y2 = min(h, y2 + pad_y)

        crop = img.crop((x1, y1, x2, y2))

        # Fill a square frame (object-cover): scale + center-crop the longer side
        # so the face fills the whole avatar — no grey letterbox bars.
        from PIL import ImageOps
        sq = ImageOps.fit(crop, (size, size), Image.LANCZOS, centering=(0.5, 0.5))
        sq.save(str(out), "JPEG", quality=88)
        return str(out)
    except Exception:
        return None
