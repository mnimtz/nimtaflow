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


# Relationship words → the role label(s) (as in RELATION_TYPES) the *other*
# person has from the reference person's perspective. Lets "Bilder meiner
# Ehefrau" / "Fotos von meinem Kollegen" resolve to actual people via the graph.
_REL_TERMS: dict[tuple, set] = {
    ("ehefrau",): {"Ehefrau"},
    ("ehemann",): {"Ehemann"},
    ("frau",): {"Ehefrau", "Partner/in"},
    ("mann",): {"Ehemann", "Partner/in"},
    ("partner", "partnerin"): {"Partner/in", "Ehefrau", "Ehemann"},
    ("kollege", "kollegin", "kollegen"): {"Kollege/in"},
    ("chef", "chefin", "vorgesetzte", "vorgesetzter", "vorgesetzten"): {"Vorgesetzte/r"},
    ("mitarbeiter", "mitarbeiterin"): {"Mitarbeiter/in"},
    ("bruder",): {"Bruder", "Geschwister"},
    ("schwester",): {"Schwester", "Geschwister"},
    ("geschwister",): {"Geschwister", "Bruder", "Schwester"},
    ("vater", "papa"): {"Vater", "Elternteil"},
    ("mutter", "mama"): {"Mutter", "Elternteil"},
    ("eltern",): {"Elternteil", "Vater", "Mutter"},
    ("sohn",): {"Sohn", "Kind"},
    ("tochter",): {"Tochter", "Kind"},
    ("kind", "kinder"): {"Kind", "Sohn", "Tochter"},
    ("opa", "großvater", "grossvater"): {"Großvater", "Großelternteil"},
    ("oma", "großmutter", "grossmutter"): {"Großmutter", "Großelternteil"},
    ("enkel", "enkelin"): {"Enkel/in"},
    ("onkel",): {"Onkel"},
    ("tante",): {"Tante"},
    ("neffe",): {"Neffe"},
    ("nichte",): {"Nichte"},
    ("cousin", "cousine"): {"Cousin/e"},
    ("freund", "freundin", "freunde"): {"Freund/in", "Beste/r Freund/in"},
    ("nachbar", "nachbarin"): {"Nachbar/in"},
    ("bekannte", "bekannter", "bekannten"): {"Bekannte/r"},
}


def _match_relation_roles(q: str) -> Optional[set]:
    words = set(re.findall(r"[a-zäöüß]+", q.lower()))
    roles: set = set()
    for terms, r in _REL_TERMS.items():
        if any(t in words for t in terms):
            roles |= r
    return roles or None


async def resolve_relationship_people(db: AsyncSession, ref_person_id: int, roles: set) -> set:
    """Person ids that have one of `roles` relative to ref_person (via the graph)."""
    from app.models.relationship import PersonRelationship, LABEL, INVERSE_LABEL
    rels = (await db.execute(select(PersonRelationship).where(or_(
        PersonRelationship.from_person_id == ref_person_id,
        PersonRelationship.to_person_id == ref_person_id,
    )))).scalars().all()
    out: set = set()
    for r in rels:
        if r.to_person_id == ref_person_id:
            role, other = LABEL.get(r.rel_type, ""), r.from_person_id   # other is LABEL of ref
        else:
            role, other = INVERSE_LABEL.get(r.rel_type, ""), r.to_person_id  # other is INVERSE of ref
        if role in roles:
            out.add(other)
    return out


async def search_photos(db: AsyncSession, query: str, settings: dict,
                        limit: int = 60, extra_conditions: Optional[list] = None) -> List[Photo]:
    q = (query or "").strip()
    if not q:
        # Kein Freitext, aber strukturelle Filter (Person/Jahr/Datum/Ort) → NICHT leer
        # zurückgeben (das war der Bug: „Fotos von Anja 2017" fiel durch), sondern genau
        # diese gefilterte Menge, neueste zuerst.
        if extra_conditions:
            sbase = [Photo.status == PhotoStatus.done, Photo.is_missing == False,  # noqa: E712
                     Photo.is_trashed == False, Photo.thumb_small.isnot(None),
                     *extra_conditions]
            return (await db.execute(
                select(Photo).where(*sbase).order_by(Photo.taken_at.desc().nullslast()).limit(limit)
            )).scalars().all()
        return []
    base = [Photo.status == PhotoStatus.done, Photo.is_missing == False,  # noqa: E712
            Photo.is_trashed == False,
            Photo.thumb_small.isnot(None),   # never return thumbnail-less photos → no grey tiles
            *(extra_conditions or [])]
    # The set of photos the caller may see — applied to EVERY match path (tags,
    # persons, relationships) AND the final fetch so a restricted account (incl. the
    # public demo) never gets a tag/person hit from outside its scope via search/chat.
    acc_sub = select(Photo.id).where(*base)
    tokens = _tokens(q)

    # ── semantic (jina-clip-v2) ───────────────────────────────────────────────
    # The query is embedded with jina's TEXT tower; photos carry a jina IMAGE
    # vector (`embedding`) AND a jina text-of-description vector (`embedding_text`),
    # all in ONE joint space. We score against both and keep the better match per
    # photo → visual hits ("rotes Auto", even if undescribed) AND description hits.
    sem: dict = {}
    try:
        from app.services import jina_embed
        vec = jina_embed.embed_text(q)
        if vec and len(vec) == 768:
            max_dist = float(settings.get("search.max_distance", "0.62") or 0.62)
            for col in (Photo.embedding, Photo.embedding_text):
                dist = col.cosine_distance(vec)
                rows = (await db.execute(
                    select(Photo.id, dist).where(*base, col.isnot(None), dist < max_dist)
                    .order_by(dist).limit(limit * 3)
                )).all()
                for pid, d in rows:
                    score = max(0.0, (max_dist - float(d)) / max_dist)
                    sem[pid] = max(sem.get(pid, 0.0), score)
    except Exception:
        # A failed sub-query leaves the session's transaction in an aborted
        # state; without rolling back, the NEXT db.execute below raises
        # PendingRollbackError, which propagated up and 502'd the whole chat.
        # Roll back so the keyword/person queries still run (degrade, not crash).
        await db.rollback()

    # ── literal / tag / person hits ──────────────────────────────────────────
    kw: dict = defaultdict(int)
    if tokens:
        try:
            for t in tokens:
                like = f"%{t}%"
                rows = (await db.execute(select(Photo.id).where(*base, or_(
                    Photo.description.ilike(like), Photo.keywords.ilike(like),
                    Photo.city.ilike(like), Photo.country.ilike(like), Photo.location_name.ilike(like),
                )))).all()
                for (pid,) in rows:
                    kw[pid] += 1
            # tags (scoped to accessible photos)
            rows = (await db.execute(
                select(PhotoTag.photo_id).join(Tag, Tag.id == PhotoTag.tag_id)
                .where(PhotoTag.photo_id.in_(acc_sub), or_(*[Tag.name.ilike(f"%{t}%") for t in tokens]))
            )).all()
            for (pid,) in rows:
                kw[pid] += 1
            # person names → that person's accessible photos
            prows = (await db.execute(
                select(Person.id).where(or_(*[Person.name.ilike(f"%{t}%") for t in tokens]))
            )).all()
            pids = [r[0] for r in prows]
            if pids:
                frows = (await db.execute(select(Face.photo_id).where(
                    Face.person_id.in_(pids), Face.photo_id.in_(acc_sub)))).all()
                for (pid,) in frows:
                    kw[pid] += 2  # a named-person match is a strong signal
        except Exception:
            # Ein fehlgeschlagener Teil-Query lässt die Transaktion abgebrochen zurück;
            # ohne Rollback würde der finale Fetch mit PendingRollbackError 500en und der
            # Chat leer antworten TROTZ vorhandener Daten. Degradieren statt crashen.
            await db.rollback()

    # ── relationship phrases ("meine ehefrau", "mein kollege") → people ───────
    try:
        roles = _match_relation_roles(q)
        self_id = settings.get("relationships.self_person_id")
        if roles and self_id:
            related = await resolve_relationship_people(db, int(self_id), roles)
            if related:
                frows = (await db.execute(select(Face.photo_id).where(
                    Face.person_id.in_(related), Face.photo_id.in_(acc_sub)))).all()
                for (pid,) in frows:
                    kw[pid] += 3  # explicit relationship resolution is the strongest signal
    except Exception:
        await db.rollback()  # don't poison the session for the final fetch below

    # ── combine & rank ────────────────────────────────────────────────────────
    # Relevance floor: a photo that ONLY matched semantically with a weak score is
    # noise (the old behaviour filled the list to `limit` with ~irrelevant images).
    # Keep it only if it had a keyword/person/relationship hit OR a decent semantic
    # score. Tunable via search.min_score.
    sem_floor = float(settings.get("search.min_score", "0.28") or 0.28)
    scores: dict = {}
    for pid, c in kw.items():
        scores[pid] = scores.get(pid, 0.0) + 10.0 + c * 2.0   # precise hits dominate
    for pid, s in sem.items():
        if pid in kw or s >= sem_floor:                        # drop weak semantic-only noise
            scores[pid] = scores.get(pid, 0.0) + s             # semantic 0..1 fills in
    if not scores:
        return []
    top = sorted(scores, key=lambda p: -scores[p])[:limit]
    # Re-apply base here too (defense in depth): nothing outside the caller's scope
    # can be returned even if a future match path forgets to scope itself.
    try:
        photos = (await db.execute(select(Photo).where(Photo.id.in_(top), *base))).scalars().all()
    except Exception:
        await db.rollback()
        photos = (await db.execute(select(Photo).where(Photo.id.in_(top), *base))).scalars().all()
    order = {pid: i for i, pid in enumerate(top)}
    photos.sort(key=lambda p: order.get(p.id, 1e9))
    return photos
