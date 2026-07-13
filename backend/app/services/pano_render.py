"""v1.563: Little-Planet & Perspektiv-Renderer für 360°-Fotos.

ffmpeg-v360-Filter macht die Konvertierung equirectangular → little_planet
oder equirectangular → rectilinear (normale Perspektive) in einem Rutsch.

Rendering ist billig (~1-2s pro Foto), landet als extra JPG im
Cache-Verzeichnis. Keine DB-Änderung nötig (via Convention:
{photo_id}_planet.jpg / {photo_id}_reframe_{i}.jpg neben den Thumbs).
"""
import os
import subprocess
import pathlib
from typing import Optional, List, Tuple


def _cache_root() -> pathlib.Path:
    p = pathlib.Path(os.environ.get("CACHE_PATH", "/cache")) / "panorama"
    p.mkdir(parents=True, exist_ok=True)
    return p


def little_planet_path(photo_id: int) -> str:
    return str(_cache_root() / f"{photo_id}_planet.jpg")


def reframe_path(photo_id: int, idx: int) -> str:
    return str(_cache_root() / f"{photo_id}_reframe_{idx}.jpg")


def render_little_planet(src_image: str, photo_id: int,
                         out_size: int = 800) -> Optional[str]:
    """Little-Planet-Ansicht aus einem equirectangularen 360°-Foto rendern.
    Nutzt ffmpeg-v360 (equirect → fisheye mit Zoom nach unten = Little Planet).
    Rückgabe: Pfad zum JPG oder None."""
    if not src_image or not os.path.exists(src_image):
        return None
    out = little_planet_path(photo_id)
    if os.path.exists(out) and os.path.getmtime(out) > os.path.getmtime(src_image):
        return out
    # v360-Filter: input equirect, output fisheye (little planet = fisheye
    # mit ihaven-view=180 und Kamera nach unten kippen).
    # pitch=-90 dreht das Bild "unter uns" in die Mitte — echter Little Planet.
    vf = (f"v360=input=equirect:output=fisheye:pitch=-90:"
          f"h_fov=210:v_fov=210:w={out_size}:h={out_size}")
    try:
        cp = subprocess.run(
            ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
             "-i", src_image, "-vf", vf, "-frames:v", "1",
             "-q:v", "3", out],
            capture_output=True, timeout=30)
        if cp.returncode == 0 and os.path.exists(out) and os.path.getsize(out) > 1000:
            return out
    except Exception:
        pass
    return None


def render_reframe(src_image: str, photo_id: int, idx: int,
                   yaw: float, pitch: float = 0.0,
                   h_fov: float = 90.0, out_size: int = 1600) -> Optional[str]:
    """Perspektivischer Ausschnitt aus einem 360°-Foto rendern.
    yaw = Blickrichtung horizontal (0=vorne, 90=rechts, 180=hinten, -90=links).
    pitch = Blickrichtung vertikal (0=Horizont, -30=leicht nach unten).
    h_fov = Bildwinkel horizontal (60=Tele, 90=normal, 120=Weitwinkel).
    Rückgabe: Pfad zum JPG oder None."""
    if not src_image or not os.path.exists(src_image):
        return None
    out = reframe_path(photo_id, idx)
    if os.path.exists(out) and os.path.getmtime(out) > os.path.getmtime(src_image):
        return out
    v_fov = max(30.0, h_fov * 9 / 16.0)   # 16:9-Verhältnis
    out_h = int(out_size * 9 / 16)
    vf = (f"v360=input=equirect:output=flat:yaw={yaw}:pitch={pitch}:"
          f"h_fov={h_fov}:v_fov={v_fov}:w={out_size}:h={out_h}")
    try:
        cp = subprocess.run(
            ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
             "-i", src_image, "-vf", vf, "-frames:v", "1",
             "-q:v", "3", out],
            capture_output=True, timeout=30)
        if cp.returncode == 0 and os.path.exists(out) and os.path.getsize(out) > 1000:
            return out
    except Exception:
        pass
    return None
