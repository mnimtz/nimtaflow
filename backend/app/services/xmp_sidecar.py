"""XMP sidecar writer (exiftool-backed, consolidated).

Writes ONE `.xmp` sidecar per media file, named `<full-name>.xmp`
(e.g. `IMG_1234.JPG.xmp`, `clip.MP4.xmp`) — the append convention used by
Immich, digiKam, Darktable ("store next to file") and exiftool's own default.
It is collision-free (a `.JPG` and a `.MOV` of the same base name get separate
sidecars) and unambiguous, unlike the older replace-extension form `IMG_1234.xmp`.

Why exiftool instead of hand-built XML: a photo's metadata is written at several
moments — the AI description/keywords when a describe job finishes, the face
regions + person names when the "write faces" button runs. exiftool MERGES into
an existing sidecar (updating only the tags it is given, preserving the rest),
so those writes accumulate into one consolidated file instead of clobbering each
other. Hand-built XML rewrote the whole file each time and dropped whatever it
wasn't given (e.g. face regions).

Legacy `IMG_1234.xmp` sidecars (the old replace-extension form PhotoFlow used to
write) are migrated on the first write: their content is seeded into the new
`IMG_1234.JPG.xmp` and the legacy file is removed, so nothing is lost and no
duplicate/stale sidecar is left behind.
"""
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

_EXIFTOOL = shutil.which("exiftool")


def file_capture_date(path: str) -> Optional[datetime]:
    """Filesystem modification time as a naive datetime — used as a fallback
    capture date for files without an EXIF DateTimeOriginal. Read-only; never
    modifies the original."""
    try:
        return datetime.fromtimestamp(os.path.getmtime(path))
    except Exception:
        return None


def sidecar_for(media_path: str) -> str:
    """The canonical sidecar path: full media name + '.xmp' (IMG_1234.JPG.xmp)."""
    return media_path + ".xmp"


def legacy_sidecar_for(media_path: str) -> str:
    """The old replace-extension sidecar path (IMG_1234.xmp) — read-only fallback
    + migration source."""
    return str(Path(media_path).with_suffix(".xmp"))


def _clean_region_name(name: str) -> str:
    """exiftool struct syntax uses { } [ ] , as delimiters — strip them from a
    person name so they can't corrupt the RegionList struct."""
    out = (name or "").strip()
    for ch in "{}[],":
        out = out.replace(ch, " ")
    return " ".join(out.split())


def write_sidecar(
    photo_path: str,
    *,
    description: Optional[str] = None,
    user_description: Optional[str] = None,
    rating: Optional[int] = None,
    keywords: Optional[list] = None,
    title: Optional[str] = None,
    artist: Optional[str] = None,
    caption: Optional[str] = None,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    city: Optional[str] = None,
    country: Optional[str] = None,
    capture_date: Optional[str] = None,
    faces: Optional[list] = None,
    width: Optional[int] = None,
    height: Optional[int] = None,
) -> str:
    """Create or update the consolidated `<name>.xmp` sidecar and return its path.

    Only the fields actually passed are written; everything already in the sidecar
    (e.g. face regions from an earlier call) is preserved. `faces` is a list of
    {cx,cy,w,h (normalized, CENTER-based), name} dicts; width/height are the source
    pixel dimensions for the MWG AppliedToDimensions.
    """
    sc = sidecar_for(photo_path)
    if not _EXIFTOOL:
        return sc

    legacy = legacy_sidecar_for(photo_path)
    # Migrate a legacy IMG.xmp into the new IMG.JPG.xmp before the first write, so
    # description/regions written under the old name are carried over (not lost).
    if not os.path.exists(sc) and legacy != sc and os.path.exists(legacy):
        try:
            subprocess.run([_EXIFTOOL, "-m", "-P", "-tagsFromFile", legacy,
                            "-all:all", "-o", sc, legacy],
                           capture_output=True, timeout=60)
        except Exception:
            pass

    exists = os.path.exists(sc)
    args = [_EXIFTOOL, "-m", "-P"]
    if not exists:
        args += ["-o", sc]          # create a fresh sidecar
    else:
        args += ["-overwrite_original"]  # merge into the existing one

    desc = user_description or description  # user text takes precedence
    if desc:
        args.append(f"-XMP-dc:Description={desc}")
    elif caption:
        args.append(f"-XMP-dc:Description={caption}")
    if title:
        args.append(f"-XMP-dc:Title={title}")
    if artist:
        args.append(f"-XMP-dc:Creator={artist}")
    if rating is not None:
        args.append(f"-XMP:Rating={max(0, min(5, int(rating)))}")
    if capture_date:
        args.append(f"-XMP:DateTimeOriginal={capture_date}")
        args.append(f"-XMP-photoshop:DateCreated={capture_date}")
    if keywords:
        args.append("-XMP-dc:Subject=")        # clear, then re-add (idempotent)
        for kw in keywords:
            args.append(f"-XMP-dc:Subject+={kw}")
    if latitude is not None and longitude is not None:
        args += [
            f"-XMP:GPSLatitude={abs(latitude)}",
            f"-XMP:GPSLatitudeRef={'N' if latitude >= 0 else 'S'}",
            f"-XMP:GPSLongitude={abs(longitude)}",
            f"-XMP:GPSLongitudeRef={'E' if longitude >= 0 else 'W'}",
        ]
    if city:
        args.append(f"-XMP-photoshop:City={city}")
        args.append(f"-XMP-iptcCore:Location={city}")
    if country:
        args.append(f"-XMP-photoshop:Country={country}")
    if faces:
        w = int(width or 0) or 1000
        h = int(height or 0) or 1000
        items, names = [], []
        for r in faces:
            try:
                area = (f"Area={{X={float(r['cx']):.4f},Y={float(r['cy']):.4f},"
                        f"W={float(r['w']):.4f},H={float(r['h']):.4f},Unit=normalized}}")
            except (KeyError, TypeError, ValueError):
                continue
            nm = _clean_region_name(r.get("name", ""))
            if nm:
                names.append(nm)
                items.append(f"{{{area},Type=Face,Name={nm}}}")
            else:
                items.append(f"{{{area},Type=Face}}")
        if items:
            region_info = (f"{{AppliedToDimensions={{W={w},H={h},Unit=pixel}},"
                           f"RegionList=[{','.join(items)}]}}")
            args.append(f"-RegionInfo={region_info}")
            args.append("-XMP:PersonInImage=")     # clear, then re-add
            for nm in dict.fromkeys(names):
                args.append(f"-XMP:PersonInImage+={nm}")

    # Create vs update: with -o the tags are written to the NEW sidecar and there
    # must be NO trailing source file (it doesn't exist yet); when updating, the
    # existing sidecar is the file to edit and IS passed as the trailing argument.
    if exists:
        args.append(sc)
    try:
        subprocess.run(args, capture_output=True, timeout=120)
    except Exception:
        return sc

    # Remove the now-migrated legacy sidecar so only the canonical one remains.
    if legacy != sc and os.path.exists(legacy) and os.path.exists(sc):
        try:
            os.remove(legacy)
        except Exception:
            pass
    return sc
