"""Filesystem browser — lists directories for the source picker."""
import os
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/fs", tags=["filesystem"])

# Only allow browsing inside these roots (safety)
ALLOWED_ROOTS = ["/", "/photos", "/mnt", "/media", "/data", "/nas", "/srv", "/home"]


class DirEntry(BaseModel):
    name: str
    path: str
    has_children: bool


class DirListing(BaseModel):
    path: str
    parent: Optional[str]
    entries: List[DirEntry]


def _is_allowed(path: str) -> bool:
    p = Path(path).resolve()
    return any(str(p).startswith(root) for root in ALLOWED_ROOTS)


@router.get("/browse", response_model=DirListing)
async def browse(path: str = Query("/", description="Directory path to list")):
    resolved = str(Path(path).resolve())
    if not _is_allowed(resolved):
        raise HTTPException(403, "Access denied")
    if not os.path.isdir(resolved):
        raise HTTPException(404, "Not a directory")

    entries: List[DirEntry] = []
    try:
        items = sorted(os.scandir(resolved), key=lambda e: e.name.lower())
    except PermissionError:
        raise HTTPException(403, "Permission denied")

    for item in items:
        if not item.is_dir(follow_symlinks=True):
            continue
        if item.name.startswith("."):
            continue
        # Quick check if it has subdirectories
        try:
            has_children = any(
                e.is_dir(follow_symlinks=True)
                for e in os.scandir(item.path)
                if not e.name.startswith(".")
            )
        except PermissionError:
            has_children = False

        entries.append(DirEntry(name=item.name, path=item.path, has_children=has_children))

    parent = str(Path(resolved).parent) if resolved != "/" else None

    return DirListing(path=resolved, parent=parent, entries=entries)
