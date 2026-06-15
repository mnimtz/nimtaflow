"""Per-user access_config enforcement.

access_config (JSON on User) may contain:
  visible_from / visible_until : ISO date strings — restrict by photo date
  folder_whitelist / folder_blacklist : list of path prefixes
  visible_person_ids : list of person ids (only photos containing them); null = all
  allow_download / allow_map / allow_share / allow_pipeline : feature flags

Admins (and unauthenticated requests when login isn't enforced) are unrestricted.
"""
from typing import List, Optional
from sqlalchemy import or_, select

from app.models.photo import Photo
from app.models.face import Face
from app.models.user import User, UserRole


def _is_unrestricted(user: Optional[User]) -> bool:
    return user is None or user.role == UserRole.admin or not (user.access_config or {})


def photo_conditions(user: Optional[User]) -> List:
    """SQLAlchemy WHERE clauses restricting a photo query to what `user` may see."""
    if _is_unrestricted(user):
        return []
    cfg = user.access_config or {}
    conds: List = []
    if cfg.get("visible_from"):
        conds.append(Photo.taken_at >= cfg["visible_from"])
    if cfg.get("visible_until"):
        conds.append(Photo.taken_at <= cfg["visible_until"])
    wl = [p for p in (cfg.get("folder_whitelist") or []) if p]
    if wl:
        conds.append(or_(*[Photo.path.like(f"{p.rstrip('/')}/%") for p in wl]))
    for p in (cfg.get("folder_blacklist") or []):
        if p:
            conds.append(~Photo.path.like(f"{p.rstrip('/')}/%"))
    pids = cfg.get("visible_person_ids")
    if pids:  # null/empty = all
        conds.append(Photo.id.in_(select(Face.photo_id).where(Face.person_id.in_(pids))))
    return conds


def can_see_photo(photo: Photo, user: Optional[User]) -> bool:
    """In-Python check for a single already-loaded photo (date + folder rules).
    Person-visibility is enforced at query level; here we cover the cheap cases."""
    if _is_unrestricted(user):
        return True
    cfg = user.access_config or {}
    if cfg.get("visible_from") and photo.taken_at and str(photo.taken_at)[:10] < cfg["visible_from"]:
        return False
    if cfg.get("visible_until") and photo.taken_at and str(photo.taken_at)[:10] > cfg["visible_until"]:
        return False
    wl = [p for p in (cfg.get("folder_whitelist") or []) if p]
    if wl and not any(photo.path.startswith(p.rstrip("/") + "/") for p in wl):
        return False
    for p in (cfg.get("folder_blacklist") or []):
        if p and photo.path.startswith(p.rstrip("/") + "/"):
            return False
    return True


def feature_allowed(user: Optional[User], flag: str, default: bool = True) -> bool:
    if user is None or user.role == UserRole.admin:
        return True
    cfg = user.access_config or {}
    return bool(cfg.get(flag, default))
