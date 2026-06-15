"""Thumbnail + video preview generation."""
import hashlib
import shutil
import subprocess
from pathlib import Path
from typing import Optional, Tuple
from PIL import Image

try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:
    pass

_FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
_FFPROBE = shutil.which("ffprobe") or "ffprobe"

SIZES = {
    "small":  (320, 320),
    "medium": (800, 800),
    "large":  (1920, 1920),
}

# ── Helpers ──────────────────────────────────────────────────────────────────

def _hash(path: str) -> str:
    return hashlib.sha256(path.encode()).hexdigest()


def _thumb_path(cache_root: str, source: str, size: str, ext: str = "jpg") -> Path:
    h = _hash(source)
    return Path(cache_root) / "thumbs" / size / h[:2] / f"{h}.{ext}"


# ── Image thumbnails ──────────────────────────────────────────────────────────

def _open_image_any(photo_path: str) -> Optional[Image.Image]:
    """Open an image, falling back to exiftool's embedded preview for HEIC/RAW
    variants that Pillow/pillow-heif can't decode."""
    is_heic = photo_path.lower().endswith((".heic", ".heif"))
    try:
        img = Image.open(photo_path)
        # Force a full decode now. Pillow/pillow-heif opens lazily and can return
        # an object that only fails (or yields a wrong-sized sub-image) on load —
        # for HEIC we'd rather fall through to heif-convert than cache that.
        img.load()
        if not is_heic:
            return img
        # Sanity-check HEIC: a decoded tile/preview is far smaller than the file's
        # declared primary dimensions. If Pillow gave us something tiny, prefer heif-convert.
        if min(img.size) >= 256:
            return img
    except Exception:
        pass
    # HEIC/HEIF that Pillow can't decode (e.g. grid/tiled): use libheif's heif-convert
    # which assembles the full image correctly (avoids the wrong "zoomed tile" crop).
    if photo_path.lower().endswith((".heic", ".heif")):
        try:
            import shutil as _sh, subprocess, tempfile, os as _os
            hc = _sh.which("heif-convert")
            if hc:
                tmp = tempfile.mktemp(suffix=".jpg")
                r = subprocess.run([hc, "-q", "92", photo_path, tmp], capture_output=True, timeout=40)
                if r.returncode == 0 and _os.path.exists(tmp) and _os.path.getsize(tmp) > 1000:
                    img = Image.open(tmp).copy()
                    _os.remove(tmp)
                    return img
                if _os.path.exists(tmp):
                    _os.remove(tmp)
        except Exception:
            pass
    # fallback: extract embedded preview via exiftool
    try:
        import shutil as _sh, subprocess, io
        exe = _sh.which("exiftool")
        if not exe:
            return None
        for tag in ("-PreviewImage", "-JpgFromRaw", "-ThumbnailImage"):
            r = subprocess.run([exe, "-b", tag, photo_path], capture_output=True, timeout=20)
            if r.returncode == 0 and r.stdout and len(r.stdout) > 1000:
                return Image.open(io.BytesIO(r.stdout))
    except Exception:
        pass
    # last resort: let ffmpeg decode one frame (handles HEIC variants without preview)
    try:
        import subprocess, tempfile, os as _os
        tmp = tempfile.mktemp(suffix=".png")
        r = subprocess.run([_FFMPEG, "-y", "-i", photo_path, "-frames:v", "1", tmp],
                           capture_output=True, timeout=30)
        if r.returncode == 0 and _os.path.exists(tmp) and _os.path.getsize(tmp) > 1000:
            img = Image.open(tmp).copy()
            _os.remove(tmp)
            return img
    except Exception:
        pass
    return None


def generate_thumbnail(photo_path: str, cache_root: str, size: str = "medium", force: bool = False) -> Optional[str]:
    """Generate JPEG thumbnail; returns path or None on failure.

    force=True ignores (and overwrites) any cached file — used by reprocess so a
    previously-cached wrong thumbnail (e.g. an old ffmpeg-tile crop) gets replaced.
    """
    out = _thumb_path(cache_root, photo_path, size)
    if out.exists() and not force:
        return str(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        img = _open_image_any(photo_path)
        if img is None:
            return None
        img = _fix_orientation(img)
        img.thumbnail(SIZES[size], Image.LANCZOS)
        img = _to_rgb(img)
        img.save(str(out), "JPEG", quality=85, optimize=True, progressive=True)
        return str(out)
    except Exception:
        return None


def generate_webp_thumbnail(photo_path: str, cache_root: str, size: str = "medium", force: bool = False) -> Optional[str]:
    """Generate WebP thumbnail (smaller file, modern browsers)."""
    out = _thumb_path(cache_root, photo_path, size, "webp")
    if out.exists() and not force:
        return str(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        img = _open_image_any(photo_path)
        if img is None:
            return None
        img = _fix_orientation(img)
        img.thumbnail(SIZES[size], Image.LANCZOS)
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGBA" if "transparency" in img.info else "RGB")
        img.save(str(out), "WEBP", quality=82, method=4)
        return str(out)
    except Exception:
        return None


def _fix_orientation(img: Image.Image) -> Image.Image:
    try:
        from PIL import ImageOps
        return ImageOps.exif_transpose(img)
    except Exception:
        return img


def _to_rgb(img: Image.Image) -> Image.Image:
    if img.mode in ("RGBA", "P", "LA"):
        bg = Image.new("RGB", img.size, (255, 255, 255))
        mask = img.split()[-1] if img.mode in ("RGBA", "LA") else None
        bg.paste(img, mask=mask)
        return bg
    return img.convert("RGB") if img.mode != "RGB" else img


def open_image_for_ai(photo_path: str, max_size: int = 1024) -> Optional[Image.Image]:
    try:
        img = _open_image_any(photo_path)  # HEIC/grid-safe (heif-convert/ffmpeg fallback)
        if img is None:
            return None
        img = _fix_orientation(img)
        img.thumbnail((max_size, max_size), Image.LANCZOS)
        return _to_rgb(img)
    except Exception:
        return None


# ── Video thumbnails ──────────────────────────────────────────────────────────

def video_duration(video_path: str) -> Optional[float]:
    """Return duration in seconds using ffprobe."""
    try:
        r = subprocess.run(
            [_FFPROBE, "-v", "quiet", "-print_format", "json",
             "-show_format", video_path],
            capture_output=True, timeout=15,
        )
        import json
        data = json.loads(r.stdout)
        return float(data["format"]["duration"])
    except Exception:
        return None


def video_dimensions(video_path: str) -> Tuple[Optional[int], Optional[int]]:
    """Return (width, height) of a video, accounting for rotation metadata
    (phone videos are often stored rotated). Returns (None, None) on failure."""
    try:
        r = subprocess.run(
            [_FFPROBE, "-v", "quiet", "-print_format", "json",
             "-show_streams", "-select_streams", "v:0", video_path],
            capture_output=True, timeout=15,
        )
        import json
        st = (json.loads(r.stdout).get("streams") or [{}])[0]
        w, h = int(st.get("width") or 0), int(st.get("height") or 0)
        if not w or not h:
            return (None, None)
        rot = 0
        tags = st.get("tags") or {}
        if tags.get("rotate"):
            rot = abs(int(tags["rotate"]))
        for sd in (st.get("side_data_list") or []):
            if "rotation" in sd:
                rot = abs(int(sd["rotation"]))
        if rot in (90, 270):
            w, h = h, w
        return (w, h)
    except Exception:
        return (None, None)


def generate_video_thumbnail(
    video_path: str,
    cache_root: str,
    size: str = "medium",
    at_second: Optional[float] = None,
    force: bool = False,
) -> Optional[str]:
    """Extract a JPEG frame from a video at `at_second` (default: 10% mark)."""
    out = _thumb_path(cache_root, video_path + ":thumb", size)
    if out.exists() and not force:
        return str(out)
    out.parent.mkdir(parents=True, exist_ok=True)

    if at_second is None:
        dur = video_duration(video_path)
        at_second = max(1.0, (dur or 10) * 0.1)

    w, h = SIZES[size]
    try:
        r = subprocess.run(
            [
                _FFMPEG, "-y",
                "-ss", str(at_second),
                "-i", video_path,
                "-vframes", "1",
                "-vf", f"scale={w}:{h}:force_original_aspect_ratio=decrease",
                "-q:v", "3",
                str(out),
            ],
            capture_output=True, timeout=30,
        )
        if r.returncode == 0 and out.exists():
            return str(out)
    except Exception:
        pass
    return None


def generate_video_preview_webp(
    video_path: str,
    cache_root: str,
    duration_sec: float = 2.0,
    fps: int = 6,
    width: int = 320,
    at_second: Optional[float] = None,
    force: bool = False,
) -> Optional[str]:
    """Generate a lightweight animated WebP hover preview (silent, looping).

    Kept cheap on purpose so it never clogs the worker pool: short clip, low
    fps, small width, single fast pass with a tight timeout. No GIF fallback.
    """
    h = _hash(video_path + ":preview")
    out = Path(cache_root) / "previews" / h[:2] / f"{h}.webp"
    if out.exists() and not force:
        return str(out)
    out.parent.mkdir(parents=True, exist_ok=True)

    dur = video_duration(video_path)
    if not dur:
        return None

    if at_second is None:
        at_second = max(0, min(dur * 0.05, max(0, dur - duration_sec - 1)))

    total_frames = int(duration_sec * fps)
    vf = f"scale={width}:-2:flags=fast_bilinear,fps={fps}"
    try:
        r = subprocess.run(
            [
                _FFMPEG, "-y",
                "-ss", str(at_second),
                "-i", video_path,
                "-t", str(duration_sec),
                "-vf", vf,
                "-vframes", str(total_frames),
                "-loop", "0",
                "-compression_level", "2",
                "-quality", "70",
                "-an",
                str(out),
            ],
            capture_output=True, timeout=20,
        )
        if r.returncode == 0 and out.exists() and out.stat().st_size > 800:
            return str(out)
    except Exception:
        pass
    return None


def generate_video_sprite(
    video_path: str,
    cache_root: str,
    cols: int = 10,
    rows: int = 10,
    thumb_w: int = 120,
    thumb_h: int = 68,
) -> Optional[Tuple[str, str]]:
    """Generate a sprite sheet (jpg) + VTT file for timeline scrubbing.

    Returns (sprite_path, vtt_path) or None.
    VTT format is compatible with videojs/plyr/custom players.
    """
    h = _hash(video_path + ":sprite")
    sprite_path = Path(cache_root) / "sprites" / h[:2] / f"{h}.jpg"
    vtt_path = sprite_path.with_suffix(".vtt")

    if sprite_path.exists() and vtt_path.exists():
        return str(sprite_path), str(vtt_path)

    sprite_path.parent.mkdir(parents=True, exist_ok=True)

    dur = video_duration(video_path)
    if not dur or dur < 1:
        return None

    total = cols * rows
    interval = dur / total

    frames_dir = sprite_path.parent / f"{h}_frames"
    frames_dir.mkdir(exist_ok=True)

    try:
        r = subprocess.run(
            [
                _FFMPEG, "-y", "-i", video_path,
                "-vf", f"fps=1/{interval:.3f},scale={thumb_w}:{thumb_h}:force_original_aspect_ratio=decrease,pad={thumb_w}:{thumb_h}:(ow-iw)/2:(oh-ih)/2",
                "-vframes", str(total),
                str(frames_dir / "frame%04d.jpg"),
            ],
            capture_output=True, timeout=120,
        )
        if r.returncode != 0:
            return None

        frames = sorted(frames_dir.glob("frame*.jpg"))
        if not frames:
            return None

        # Stitch sprite sheet
        sprite_img = Image.new("RGB", (cols * thumb_w, rows * thumb_h), (0, 0, 0))
        for idx, fp in enumerate(frames[:total]):
            try:
                fr = Image.open(fp)
                x = (idx % cols) * thumb_w
                y = (idx // cols) * thumb_h
                sprite_img.paste(fr, (x, y))
            except Exception:
                pass
        sprite_img.save(str(sprite_path), "JPEG", quality=80, optimize=True)

        # Write VTT
        lines = ["WEBVTT", ""]
        sprite_url = f"/api/photos/sprite/{h}"
        for idx, fr_path in enumerate(frames[:total]):
            t_start = idx * interval
            t_end = t_start + interval
            x = (idx % cols) * thumb_w
            y = (idx // cols) * thumb_h
            lines += [
                f"{_vtt_time(t_start)} --> {_vtt_time(t_end)}",
                f"{sprite_url}#xywh={x},{y},{thumb_w},{thumb_h}",
                "",
            ]
        vtt_path.write_text("\n".join(lines))

        return str(sprite_path), str(vtt_path)
    except Exception:
        return None
    finally:
        import shutil as _shutil
        _shutil.rmtree(frames_dir, ignore_errors=True)


def _vtt_time(sec: float) -> str:
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = sec % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"
