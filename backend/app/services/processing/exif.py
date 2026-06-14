"""Extract EXIF metadata from image files."""
import struct
from datetime import datetime
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

try:
    import exifread
except ImportError:
    exifread = None

try:
    from PIL import Image
    from PIL.ExifTags import TAGS, GPSTAGS
except ImportError:
    Image = None


@dataclass
class ExifData:
    taken_at: Optional[datetime] = None
    width: Optional[int] = None
    height: Optional[int] = None
    camera_make: Optional[str] = None
    camera_model: Optional[str] = None
    lens_model: Optional[str] = None
    focal_length: Optional[float] = None
    aperture: Optional[float] = None
    shutter_speed: Optional[str] = None
    iso: Optional[int] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    altitude: Optional[float] = None


def _dms_to_decimal(dms, ref) -> Optional[float]:
    try:
        d, m, s = float(dms[0]), float(dms[1]), float(dms[2])
        decimal = d + m / 60 + s / 3600
        if ref in ("S", "W"):
            decimal = -decimal
        return decimal
    except Exception:
        return None


def extract_exif(path: str) -> ExifData:
    result = ExifData()
    try:
        if Image:
            img = Image.open(path)
            result.width, result.height = img.size

            raw = img._getexif()
            if raw:
                exif = {TAGS.get(k, k): v for k, v in raw.items()}

                if "DateTimeOriginal" in exif:
                    try:
                        result.taken_at = datetime.strptime(exif["DateTimeOriginal"], "%Y:%m:%d %H:%M:%S")
                    except ValueError:
                        pass

                result.camera_make = str(exif.get("Make", "")).strip() or None
                result.camera_model = str(exif.get("Model", "")).strip() or None
                result.lens_model = str(exif.get("LensModel", "")).strip() or None

                if "FocalLength" in exif:
                    try:
                        fl = exif["FocalLength"]
                        result.focal_length = float(fl.numerator) / float(fl.denominator)
                    except Exception:
                        pass

                if "FNumber" in exif:
                    try:
                        fn = exif["FNumber"]
                        result.aperture = float(fn.numerator) / float(fn.denominator)
                    except Exception:
                        pass

                if "ISOSpeedRatings" in exif:
                    try:
                        result.iso = int(exif["ISOSpeedRatings"])
                    except Exception:
                        pass

                if "ExposureTime" in exif:
                    try:
                        et = exif["ExposureTime"]
                        n, d = et.numerator, et.denominator
                        result.shutter_speed = f"1/{d//n}" if n == 1 else f"{n}/{d}"
                    except Exception:
                        pass

                # GPS
                gps_raw = exif.get("GPSInfo")
                if gps_raw:
                    gps = {GPSTAGS.get(k, k): v for k, v in gps_raw.items()}
                    if "GPSLatitude" in gps and "GPSLatitudeRef" in gps:
                        result.latitude = _dms_to_decimal(gps["GPSLatitude"], gps["GPSLatitudeRef"])
                    if "GPSLongitude" in gps and "GPSLongitudeRef" in gps:
                        result.longitude = _dms_to_decimal(gps["GPSLongitude"], gps["GPSLongitudeRef"])
                    if "GPSAltitude" in gps:
                        try:
                            alt = gps["GPSAltitude"]
                            result.altitude = float(alt.numerator) / float(alt.denominator)
                        except Exception:
                            pass

    except Exception:
        pass

    # Fallback via exiftool — PIL can't read GPS/dates from HEIC or videos (MOV).
    if result.latitude is None or result.taken_at is None:
        _exiftool_fallback(path, result)

    return result


def _exiftool_fallback(path: str, result: "ExifData") -> None:
    import shutil, subprocess, json as _json
    exe = shutil.which("exiftool")
    if not exe:
        return
    try:
        r = subprocess.run(
            [exe, "-n", "-j",
             "-GPSLatitude", "-GPSLongitude", "-GPSAltitude",
             "-DateTimeOriginal", "-CreateDate", "-Make", "-Model", "-LensModel", path],
            capture_output=True, timeout=20,
        )
        data = _json.loads(r.stdout or "[]")
        if not data:
            return
        d = data[0]
        if result.latitude is None and d.get("GPSLatitude") is not None and d.get("GPSLongitude") is not None:
            result.latitude = float(d["GPSLatitude"])
            result.longitude = float(d["GPSLongitude"])
            if d.get("GPSAltitude") is not None:
                try:
                    result.altitude = float(d["GPSAltitude"])
                except (TypeError, ValueError):
                    pass
        if result.taken_at is None:
            for key in ("DateTimeOriginal", "CreateDate"):
                v = d.get(key)
                if v:
                    try:
                        result.taken_at = datetime.strptime(str(v)[:19], "%Y:%m:%d %H:%M:%S")
                        break
                    except ValueError:
                        continue
        if not result.camera_make and d.get("Make"):
            result.camera_make = str(d["Make"]).strip()
        if not result.camera_model and d.get("Model"):
            result.camera_model = str(d["Model"]).strip()
        if not result.lens_model and d.get("LensModel"):
            result.lens_model = str(d["LensModel"]).strip()
    except Exception:
        pass
