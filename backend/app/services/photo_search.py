"""Shared smart photo search — used by the semantic search endpoint and AI albums.

Combines several signals so results are far better than any single one:
  • semantic embedding similarity (pgvector cosine) — catches paraphrases / other
    languages even when no exact word matches
  • literal hits in description / keywords / city / country / location
  • tag matches
  • person-name matches (→ that person's photos)

Each signal contributes to a score; literal/person/tag hits are weighted strongly
(precise), semantic distance fills in the rest (recall). Degrades gracefully:
with no embedding provider it's keyword-only; with no keywords it's pure semantic.
"""
import re
import math
from collections import defaultdict
from typing import List, Optional

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.photo import Photo, PhotoStatus
from app.models.tag import Tag, PhotoTag
from app.models.face import Face
from app.models.person import Person

_STOP = {"der", "die", "das", "ein", "eine", "einen", "und", "oder", "mit", "von", "vom",
         "auf", "im", "in", "den", "dem", "des", "bei", "beim", "zur", "zum", "the", "and",
         "with", "from", "for", "are", "was", "ist", "sind", "ein", "aus"}


def _tokens(q: str) -> List[str]:
    return [t for t in re.findall(r"[\wäöüÄÖÜß]{3,}", q.lower()) if t not in _STOP]


async def search_photos(db: AsyncSession, query: str, settings: dict,
                        limit: int = 60, extra_conditions: Optional[list] = None) -> List[Photo]:
    q = (query or "").strip()
    if not q:
        return []
    base = [Photo.status == PhotoStatus.done, Photo.is_missing == False,  # noqa: E712
            Photo.is_trashed == False, *(extra_conditions or [])]
    tokens = _tokens(q)

    # ── semantic ────────────────────────────────────────────────────────────
    sem: dict = {}
    try:
        from app.services.ai.manager import AIManager
        vec, _ = await AIManager(settings).embed_text(q)
        if vec:
            if len(vec) > 768:
                vec = vec[:768]
                nrm = math.sqrt(sum(x * x for x in vec)) or 1.0
                vec = [x / nrm for x in vec]
            if len(vec) == 768:
                max_dist = float(settings.get("search.max_distance", "0.78") or 0.78)
                dist = Photo.embedding.cosine_distance(vec)
                rows = (await db.execute(
                    select(Photo.id, dist).where(*base, Photo.embedding.isnot(None), dist < max_dist)
                    .order_by(dist).limit(limit * 3)
                )).all()
                for pid, d in rows:
                    sem[pid] = max(0.0, (max_dist - float(d)) / max_dist)
    except Exception:
        pass

    # ── literal / tag / person hits ──────────────────────────────────────────
    kw: dict = defaultdict(int)
    if tokens:
        for t in tokens:
            like = f"%{t}%"
            rows = (await db.execute(select(Photo.id).where(*base, or_(
                Photo.description.ilike(like), Photo.keywords.ilike(like),
                Photo.city.ilike(like), Photo.country.ilike(like), Photo.location_name.ilike(like),
            )))).all()
            for (pid,) in rows:
                kw[pid] += 1
        # tags
        rows = (await db.execute(
            select(PhotoTag.photo_id).join(Tag, Tag.id == PhotoTag.tag_id)
            .where(or_(*[Tag.name.ilike(f"%{t}%") for t in tokens]))
        )).all()
        for (pid,) in rows:
            kw[pid] += 1
        # person names → that person's photos
        prows = (await db.execute(
            select(Person.id).where(or_(*[Person.name.ilike(f"%{t}%") for t in tokens]))
        )).all()
        pids = [r[0] for r in prows]
        if pids:
            frows = (await db.execute(select(Face.photo_id).where(Face.person_id.in_(pids)))).all()
            for (pid,) in frows:
                kw[pid] += 2  # a named-person match is a strong signal

    # ── combine & rank ────────────────────────────────────────────────────────
    scores: dict = {}
    for pid, c in kw.items():
        scores[pid] = scores.get(pid, 0.0) + 10.0 + c * 2.0   # precise hits dominate
    for pid, s in sem.items():
        scores[pid] = scores.get(pid, 0.0) + s                 # semantic 0..1 fills in
    if not scores:
        return []
    top = sorted(scores, key=lambda p: -scores[p])[:limit]
    photos = (await db.execute(select(Photo).where(Photo.id.in_(top)))).scalars().all()
    order = {pid: i for i, pid in enumerate(top)}
    photos.sort(key=lambda p: order.get(p.id, 1e9))
    return photos
