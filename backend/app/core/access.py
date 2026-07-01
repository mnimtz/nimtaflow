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


def _esc(s: str) -> str:
    """Escape LIKE wildcards so a path with '_' or '%' isn't treated as a pattern."""
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def photo_conditions(user: Optional[User]) -> List:
    """SQLAlchemy WHERE clauses restricting a photo query to what `user` may see.
    `Photo.is_hidden == False` is applied to EVERYONE (incl. admin) — a folder marked
    in display.hidden_folders disappears from all display; face recognition is
    unaffected because the workers never call this."""
    base: List = [Photo.is_hidden == False]  # noqa: E712 — global display-hide
    if _is_unrestricted(user):
        return base
    cfg = user.access_config or {}
    conds: List = list(base)   # hidden-folder filter applies to restricted users too
    if cfg.get("visible_from"):
        conds.append(Photo.taken_at >= cfg["visible_from"])
    if cfg.get("visible_until"):
        conds.append(Photo.taken_at <= cfg["visible_until"])
    wl = [p for p in (cfg.get("folder_whitelist") or []) if p]
    if wl:
        conds.append(or_(*[Photo.path.like(f"{_esc(p.rstrip('/'))}/%", escape="\\") for p in wl]))
    for p in (cfg.get("folder_blacklist") or []):
        if p:
            conds.append(~Photo.path.like(f"{_esc(p.rstrip('/'))}/%", escape="\\"))
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


async def user_can_access_photo(db, photo_id: int, user: Optional[User]) -> bool:
    """Authoritative single-photo access check — the ONE to use before returning,
    streaming, mutating or deleting a photo by id. Unlike `can_see_photo` (which by
    design only covers date + folder rules), this ALSO enforces `visible_person_ids`:
    a person-whitelist-only account otherwise passed `can_see_photo` for EVERY photo
    (it has no folder/date rules) and could read/change/hard-delete foreign photos via
    the v1 single-photo endpoints. Query-based so it applies the exact same WHERE as
    the list endpoints. Unrestricted (admin/open) short-circuits to True."""
    if _is_unrestricted(user):
        return True
    return bool(await db.scalar(
        select(Photo.id).where(Photo.id == photo_id, *photo_conditions(user))))


def visible_person_subquery(user: Optional[User]):
    """A SELECT of person_ids the user may see. Returns None when unrestricted.

    WICHTIG: Ist `visible_person_ids` explizit gesetzt, sind das GENAU die sichtbaren
    Personen — NICHT aus den zugänglichen Fotos ableiten. Sonst würden per Co-Vorkommen
    (die erlaubten Personen tauchen in Gruppenfotos mit anderen auf) fremde Personen
    sichtbar → Leck: der Nutzer sähe faktisch alle Personen/Gesichter."""
    if _is_unrestricted(user):
        return None
    cfg = user.access_config or {}
    pids = cfg.get("visible_person_ids")
    if pids:
        from app.models.person import Person
        return select(Person.id).where(Person.id.in_(pids))
    # Kein Personen-Whitelist (nur Ordner-/Datums-Scope) → Personen in zugänglichen Fotos.
    return select(Face.person_id).where(
        Face.photo_id.in_(select(Photo.id).where(*photo_conditions(user)))
    )


def upload_base_dir(user: Optional[User], default_dir: str) -> str:
    """The user's personal upload root. A restricted account uploads into its own
    tree (home_root, else the first folder_whitelist entry) so uploads never mix
    between users and stay visible to (only) that user via the folder rules.
    Unrestricted (admin/open) → the configured default dir."""
    cfg = (user.access_config or {}) if user else {}
    if cfg.get("home_root"):
        base = cfg["home_root"]
    else:
        wl = [p for p in (cfg.get("folder_whitelist") or []) if p]
        base = wl[0] if wl else default_dir
    return (base or default_dir).rstrip("/")


def user_scope_prefixes(user: Optional[User]) -> List[str]:
    """The folder prefixes a restricted user is confined to (home_root + whitelist).
    Empty list means 'no confinement configured'."""
    cfg = (user.access_config or {}) if user else {}
    out = []
    if cfg.get("home_root"):
        out.append(cfg["home_root"])
    out.extend(p for p in (cfg.get("folder_whitelist") or []) if p)
    return [p.rstrip("/") for p in out if p]


def path_within_user_scope(user: Optional[User], path: str) -> bool:
    """True if `path` is inside the user's allowed area — the gate for letting a
    non-admin add their OWN source folder (Upload-Phase 3). SECURITY-critical: uses
    realpath so neither '..' nor a symlink can escape the allowed prefix. Admin /
    unrestricted may use any path; a restricted user with NO configured scope is
    denied (can't add sources at all)."""
    import os
    if _is_unrestricted(user):
        return True
    prefixes = user_scope_prefixes(user)
    if not prefixes:
        return False
    try:
        real = os.path.realpath(path)
    except Exception:
        return False
    for pre in prefixes:
        rpre = os.path.realpath(pre)
        if real == rpre or real.startswith(rpre + os.sep):
            return True
    return False


def feature_allowed(user: Optional[User], flag: str, default: bool = True) -> bool:
    if user is None or user.role == UserRole.admin:
        return True
    cfg = user.access_config or {}
    return bool(cfg.get(flag, default))
