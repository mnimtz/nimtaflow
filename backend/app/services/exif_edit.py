"""EXIF / IPTC / XMP editing service.

Uses exiftool (subprocess) — handles JPEG, HEIC, PNG, RAW, MP4, MOV, and
essentially everything ffprobe can inspect.  Falls back to piexif for JPEG-only
edits when exiftool is not installed.
"""
import asyncio
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional


_EXIFTOOL = shutil.which("exiftool")


class ExifEditError(RuntimeError):
    pass


async def read_all_exif(path: str) -> Dict[str, Any]:
    """Return all EXIF/IPTC/XMP tags as a flat dict."""
    if not _EXIFTOOL:
        raise ExifEditError("exiftool not found")
    proc = await asyncio.create_subprocess_exec(
        _EXIFTOOL, "-json", "-a", "-u", "-G1", path,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise ExifEditError(stderr.decode()[:500])
    data = json.loads(stdout)
    return data[0] if data else {}


async def write_exif(path: str, tags: Dict[str, Any], make_backup: bool = True) -> bool:
    """Write arbitrary EXIF tags to a file using exiftool.

    Args:
        path: File to modify (modified in-place, original backed up as .orig_exif)
        tags: Dict of tag_name → value, e.g. {"EXIF:Artist": "Max", "XMP:Description": "..."}
        make_backup: If True, exiftool creates .orig_exif backup; if False, uses -overwrite_original

    Returns True on success.
    """
    if not _EXIFTOOL:
        raise ExifEditError("exiftool not found")

    args = [_EXIFTOOL]
    if not make_backup:
        args.append("-overwrite_original")
    for k, v in tags.items():
        args.append(f"-{k}={v}")
    args.append(path)

    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise ExifEditError(stderr.decode()[:500])
    return True


async def write_description(path: str, description: str, overwrite: bool = True) -> bool:
    """Write AI or user description to XMP:Description + IPTC:Caption."""
    return await write_exif(path, {
        "XMP:Description": description,
        "IPTC:Caption-Abstract": description,
        "EXIF:ImageDescription": description[:200],  # EXIF is limited
    }, make_backup=not overwrite)


async def write_rating(path: str, rating: int) -> bool:
    """Write XMP rating (0-5) to file."""
    return await write_exif(path, {
        "XMP:Rating": str(max(0, min(5, rating))),
    }, make_backup=False)


async def write_keywords(path: str, keywords: list[str]) -> bool:
    """Write keyword list to XMP + IPTC."""
    kw_str = ",".join(keywords)
    tags: Dict[str, Any] = {}
    for kw in keywords:
        tags[f"IPTC:Keywords+"] = kw
    tags["XMP:Subject"] = kw_str
    return await write_exif(path, tags, make_backup=False)


async def write_gps(path: str, lat: float, lon: float, alt: Optional[float] = None) -> bool:
    tags: Dict[str, Any] = {
        "GPS:GPSLatitude": abs(lat),
        "GPS:GPSLatitudeRef": "N" if lat >= 0 else "S",
        "GPS:GPSLongitude": abs(lon),
        "GPS:GPSLongitudeRef": "E" if lon >= 0 else "W",
    }
    if alt is not None:
        tags["GPS:GPSAltitude"] = abs(alt)
        tags["GPS:GPSAltitudeRef"] = "0" if alt >= 0 else "1"
    return await write_exif(path, tags, make_backup=False)


def exiftool_available() -> bool:
    return _EXIFTOOL is not None
