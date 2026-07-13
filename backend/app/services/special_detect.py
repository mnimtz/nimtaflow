"""v1.561: 360°-Foto/Video- und Drohnen-Erkennung.

Wird vom Scanner + Batch-Backfill aufgerufen. Setzt Photo.is_360 / is_drone
und extrahiert relevante Metadaten in pano_metadata / drone_metadata (JSONB).

Erkennungs-Reihenfolge:
1. XMP-GPano:ProjectionType == equirectangular       → 360° (härtester Beweis)
2. EXIF-Make/Model matcht bekannte 360°-Kameras       → 360°
3. Aspect-Ratio 2:1 + Panorama-Filename-Muster        → 360° (schwach, nur fallback)
4. EXIF-Make/Model matcht bekannte Drohnen-Hersteller → Drohne
5. Filename-Muster (DJI_*, HOVER_*, XPRO_*)           → Drohne (fallback)
6. Positive relative Altitude in XMP                  → Drohne

Für die iOS-App: der User hat Insta360 One X2 + HoverAir X1 ProMax.
Beide sind hier explizit in den Erkennungs-Regeln.
"""
import os
import re
import subprocess
from typing import Optional

_EXIFTOOL = "exiftool"

# EXIF Make/Model-Signaturen die als 360° gelten
_MAKES_360 = (
    "arashi vision",   # Insta360 (offizieller EXIF-Hersteller-Name)
    "insta360",
    "ricoh",           # Theta
    "samsung",         # Gear 360 (nur wenn Model matcht)
    "gopro",           # Max
    "kandao",          # QooCam
    "lg electronics",  # LG 360 Cam
    "detu",
    "z cam",
)
_MODELS_360 = (
    "onex", "onerx",
    "insta360",
    "theta",
    "gear 360",
    "gopro max", "hero max",
    "qoocam",
    "z cam s1",
    "fixframe",        # Insta360 One R FixFrame
)
# Modelle die als Ganzwort erscheinen müssen (verhindert dass "one x" in "iphone x" matched)
_MODELS_360_WORD = (
    r"\bone\s*x\b",
    r"\bone\s*r\b",
    r"\bone\s*rx\b",
)

# EXIF Make/Model-Signaturen für Drohnen
_MAKES_DRONE = (
    "dji",
    "zero zero",
    "hover",
    "autel",
    "skydio",
    "parrot",
    "yuneec",
)
_MODELS_DRONE = (
    "dji", "mavic", "phantom", "spark", "inspire", "mini", "air", "avata",
    "hoverair", "hover x", "hover ", "x1 promax", "x1promax",
    "evo", "nano", "lite",         # Autel
    "skydio", "r1", "r2", "s2",
    "anafi", "bebop", "disco",     # Parrot
    "typhoon", "mantis",           # Yuneec
)

# Filename-Muster (Fallback wenn EXIF fehlt)
_FN_DRONE = re.compile(r"^(DJI|HOVER|XPRO|MAVIC|AUTEL|SKYDIO)[_\-0-9]", re.IGNORECASE)
_FN_360   = re.compile(r"(^|[_\-])(IMG_[0-9]+_[0-9]+_00_[0-9]+|INSTA360|360|PANO)", re.IGNORECASE)


def _exiftool_json(path: str) -> dict:
    """Fokussierter exiftool-Call — nur die Felder die wir für Detection brauchen."""
    try:
        cp = subprocess.run([
            _EXIFTOOL, "-j", "-fast", "-n",
            "-Make", "-Model", "-CameraModelName",
            "-XMP-GPano:ProjectionType", "-XMP-GPano:UsePanoramaViewer",
            "-XMP-GPano:FullPanoWidthPixels", "-XMP-GPano:CroppedAreaImageWidthPixels",
            "-XMP-drone-dji:RelativeAltitude", "-XMP-drone-dji:AbsoluteAltitude",
            "-XMP-drone-dji:GimbalPitchDegree", "-XMP-drone-dji:GimbalYawDegree",
            "-XMP-drone-dji:FlightYawDegree",
            "-ProjectionType", "-UsePanoramaViewer",
            "-ImageWidth", "-ImageHeight", "-GPSAltitude",
            path
        ], capture_output=True, timeout=15)
        import json as _j
        arr = _j.loads(cp.stdout.decode() or "[]")
        return arr[0] if arr else {}
    except Exception:
        return {}


def detect_special(path: str, filename: Optional[str] = None) -> dict:
    """Analysiert ein Medium und liefert:
        { is_360: bool, is_drone: bool,
          pano_metadata: dict|None, drone_metadata: dict|None }

    Non-invasive: liest nur, schreibt nicht. Sichere Defaults bei Fehler."""
    filename = filename or os.path.basename(path or "")
    result = {"is_360": False, "is_drone": False,
              "pano_metadata": None, "drone_metadata": None}
    if not path or not os.path.exists(path):
        return result

    md = _exiftool_json(path)
    make = str(md.get("Make", "") or "").lower()
    model = str(md.get("Model", "") or md.get("CameraModelName", "") or "").lower()
    proj = str(md.get("ProjectionType", "") or "").lower()
    use_pano = md.get("UsePanoramaViewer")
    w = int(md.get("ImageWidth") or 0)
    h = int(md.get("ImageHeight") or 0)

    # ── 360° Erkennung ────────────────────────────────────────────────────────
    is_360 = False
    if proj == "equirectangular" or use_pano is True or use_pano == "True":
        is_360 = True
    if not is_360 and any(m in make for m in _MAKES_360):
        # zusätzlich Model-Filter um "Samsung Galaxy S" (kein 360) auszuschließen
        if not (make == "samsung" and "gear 360" not in model):
            is_360 = True
    if not is_360 and any(m in model for m in _MODELS_360):
        is_360 = True
    if not is_360 and any(re.search(p, model) for p in _MODELS_360_WORD):
        is_360 = True
    # Nur Aspect-Ratio 2:1 als 360°-Fallback: sehr schwach — nur wenn Filename hinweist
    if not is_360 and w and h and abs(w / h - 2.0) < 0.05 and _FN_360.search(filename):
        is_360 = True

    if is_360:
        result["is_360"] = True
        result["pano_metadata"] = {
            "projection": proj or "equirectangular",
            "full_pano_width_px": md.get("FullPanoWidthPixels") or w,
            "width": w, "height": h,
            "source": "exif+xmp" if proj else "make_model",
        }

    # ── Drohne Erkennung ──────────────────────────────────────────────────────
    is_drone = False
    if any(m in make for m in _MAKES_DRONE):
        is_drone = True
    if not is_drone and any(m in model for m in _MODELS_DRONE):
        is_drone = True
    if not is_drone and _FN_DRONE.match(filename):
        is_drone = True
    # RelativeAltitude vorhanden → sehr wahrscheinlich Drohne (kann Handy-GPS auch
    # haben, aber XMP-drone-dji-Namespace ist drohnen-spezifisch)
    if not is_drone and (md.get("RelativeAltitude") is not None):
        is_drone = True

    if is_drone:
        rel_alt = md.get("RelativeAltitude")
        abs_alt = md.get("AbsoluteAltitude") or md.get("GPSAltitude")
        result["is_drone"] = True
        result["drone_metadata"] = {
            "relative_altitude_m": float(rel_alt) if rel_alt is not None else None,
            "absolute_altitude_m": float(abs_alt) if abs_alt is not None else None,
            "gimbal_pitch": md.get("GimbalPitchDegree"),
            "gimbal_yaw":   md.get("GimbalYawDegree"),
            "flight_yaw":   md.get("FlightYawDegree"),
            "make":  make or None,
            "model": model or None,
        }

    return result


def available() -> bool:
    try:
        subprocess.run([_EXIFTOOL, "-ver"], capture_output=True, timeout=3)
        return True
    except Exception:
        return False
