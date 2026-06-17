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


async def read_existing_ai_metadata(path: str):
    """Read an already-present description + keywords from the file's embedded
    XMP/IPTC, or from a `.xmp` sidecar next to it. Returns (description, keywords).

    Used on scan to SKIP re-running AI on media that PhotoFlow (or another tool)
    already described — e.g. after a re-import or DB loss, the descriptions we
    wrote into the files are read back instead of recomputed."""
    if not _EXIFTOOL:
        return None, []

    async def _read(target: str):
        try:
            proc = await asyncio.create_subprocess_exec(
                _EXIFTOOL, "-json", "-XMP:Description", "-IPTC:Caption-Abstract",
                "-EXIF:ImageDescription", "-XMP:Subject", "-IPTC:Keywords", target,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            out, _ = await proc.communicate()
            if proc.returncode != 0 or not out:
                return None, []
            d = (json.loads(out) or [{}])[0]
            desc = (d.get("Description") or d.get("Caption-Abstract") or d.get("ImageDescription") or "").strip() or None
            subj = d.get("Subject") or d.get("Keywords") or []
            if isinstance(subj, str):
                subj = [s.strip() for s in subj.split(",") if s.strip()]
            return desc, [str(s).strip() for s in subj if str(s).strip()]
        except Exception:
            return None, []

    desc, kws = await _read(path)
    if not desc:  # fall back to a sidecar (videos always use one; images may)
        from pathlib import Path as _P
        sc = _P(path).with_suffix(".xmp")
        if sc.exists():
            desc, kws2 = await _read(str(sc))
            kws = kws or kws2
    return desc, kws


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

    args = [_EXIFTOOL, "-m"]  # -m: ignore minor warnings (e.g. IPTC/EXIF length
    #     limits) so they never block the write — XMP still receives the full text.
    # -P: preserve the filesystem modification date. Without it exiftool sets
    # FileModifyDate to "now", which would become the photo's date for any file
    # lacking an EXIF capture date (scanner/Immich fall back to file mtime). We
    # only ever write the caller's tags (description/caption/keywords/…) and
    # NEVER DateTimeOriginal/CreateDate, so the real capture date is untouched.
    args.append("-P")
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
    """Write AI or user description to XMP:Description (+ IPTC/EXIF mirrors).

    XMP:Description is the authoritative field and has NO length limit — the full
    description is always embedded there. IPTC:Caption-Abstract has a 2000-byte
    standard limit and EXIF:ImageDescription is a legacy ASCII field; both get the
    full text too (write_exif passes -m so a length warning never blocks the
    write — XMP still gets everything)."""
    return await write_exif(path, {
        "XMP:Description": description,
        "IPTC:Caption-Abstract": description,
        "EXIF:ImageDescription": description,
    }, make_backup=not overwrite)


async def ensure_capture_date(path: str) -> Optional[str]:
    """If the file has NO DateTimeOriginal, copy its filesystem date into the EXIF
    capture-date tags. Photos without a capture date otherwise have no stable
    date at all (and a re-import elsewhere would fall back to "now"). Returns the
    date string written ("YYYY:MM:DD HH:MM:SS"), or None if it already had one /
    on failure. Uses -P so writing does NOT itself bump the filesystem mtime.
    Never overwrites an existing DateTimeOriginal."""
    if not _EXIFTOOL:
        return None
    try:
        proc = await asyncio.create_subprocess_exec(
            _EXIFTOOL, "-s3", "-DateTimeOriginal", path,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        out, _ = await proc.communicate()
        if out.decode(errors="replace").strip():
            return None  # capture date already present — leave it untouched
        # Copy the filesystem mod-date into the EXIF capture-date tags.
        proc = await asyncio.create_subprocess_exec(
            _EXIFTOOL, "-P", "-overwrite_original",
            "-DateTimeOriginal<FileModifyDate", "-CreateDate<FileModifyDate",
            "-XMP:DateTimeOriginal<FileModifyDate", path,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
        if proc.returncode != 0:
            return None
        proc = await asyncio.create_subprocess_exec(
            _EXIFTOOL, "-s3", "-DateTimeOriginal", path,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        out, _ = await proc.communicate()
        return out.decode(errors="replace").strip() or None
    except Exception:
        return None


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
