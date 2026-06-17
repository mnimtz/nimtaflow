"""Person relationships — family/social graph (Stammbaum)."""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, and_, delete as sql_delete
from pydantic import BaseModel

from app.core.database import get_db
from app.models.person import Person
from app.models.face import Face
from app.models.relationship import (
    PersonRelationship, RELATION_TYPES, DIRECTED, CATEGORY, LABEL, INVERSE_LABEL,
    PARENT_TYPES, CATEGORY_LABELS, meta,
)

router = APIRouter(prefix="/relationships", tags=["relationships"])


class RelCreate(BaseModel):
    from_person_id: int
    to_person_id: int
    rel_type: str
    note: Optional[str] = None


def _edge(r: PersonRelationship) -> dict:
    return {
        "id": r.id, "from": r.from_person_id, "to": r.to_person_id,
        "type": r.rel_type, "label": LABEL.get(r.rel_type, r.rel_type),
        "category": CATEGORY.get(r.rel_type, "other"),
        "directed": r.rel_type in DIRECTED, "note": r.note,
    }


@router.get("/graph")
async def graph(category: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    """Only persons that are IN at least one relationship (+ the relationships) —
    NOT every person. Dumping all 70+ persons (incl. dozens of unnamed clusters)
    overwhelmed the view. Optional `category` (familie | sozial | …) shows just
    that relationship category — a separate graph per area, as requested."""
    rels = (await db.execute(select(PersonRelationship))).scalars().all()
    if category:
        rels = [r for r in rels if CATEGORY.get(r.rel_type, "other") == category]
    ids = {i for r in rels for i in (r.from_person_id, r.to_person_id)}
    if not ids:
        return {"nodes": [], "edges": []}
    persons = (await db.execute(
        select(Person).where(Person.id.in_(ids)).order_by(Person.name))).scalars().all()
    counts = dict((await db.execute(
        select(Face.person_id, func.count()).where(Face.person_id.in_(ids)).group_by(Face.person_id)
    )).all())
    nodes = [{
        "id": p.id, "name": p.name or "Unbekannt", "named": bool((p.name or "").strip()),
        "face_count": counts.get(p.id, 0), "profile_face_id": p.profile_face_id,
    } for p in persons]
    return {"nodes": nodes, "edges": [_edge(r) for r in rels]}


@router.get("/person/{person_id}")
async def for_person(person_id: int, db: AsyncSession = Depends(get_db)):
    """Relationships of one person, resolved with the other person's name and a
    label from THIS person's perspective (for the person detail page)."""
    rels = (await db.execute(
        select(PersonRelationship).where(
            or_(PersonRelationship.from_person_id == person_id, PersonRelationship.to_person_id == person_id)
        )
    )).scalars().all()
    other_ids = {(r.to_person_id if r.from_person_id == person_id else r.from_person_id) for r in rels}
    names = dict((await db.execute(select(Person.id, Person.name).where(Person.id.in_(other_ids or {0})))).all())
    # human label from THIS person's point of view
    out = []
    for r in rels:
        outgoing = r.from_person_id == person_id
        oid = r.to_person_id if outgoing else r.from_person_id
        t = r.rel_type
        is_directed = t in DIRECTED
        label = LABEL.get(t, t) if (outgoing or not is_directed) else INVERSE_LABEL.get(t, LABEL.get(t, t))
        out.append({
            "id": r.id, "other_id": oid, "other_name": names.get(oid) or "Unbekannt",
            "type": t, "category": CATEGORY.get(t, "other"), "label": label, "outgoing": outgoing,
        })
    return sorted(out, key=lambda e: e["label"])


@router.get("/together/{a_id}/{b_id}")
async def photos_together(a_id: int, b_id: int, limit: int = 200, db: AsyncSession = Depends(get_db)):
    """Photos in which BOTH persons appear (faces of each on the same photo)."""
    from app.models.photo import Photo
    from app.schemas.photo import PhotoBase
    fa = select(Face.photo_id).where(Face.person_id == a_id)
    fb = select(Face.photo_id).where(Face.person_id == b_id)
    q = (select(Photo).where(Photo.id.in_(fa), Photo.id.in_(fb), Photo.is_trashed == False)  # noqa: E712
         .order_by(Photo.taken_at.desc()).limit(limit))
    photos = (await db.execute(q)).scalars().all()
    return {"count": len(photos), "items": [PhotoBase.model_validate(p, from_attributes=True) for p in photos]}


@router.post("/derive")
async def derive_relationships(db: AsyncSession = Depends(get_db)):
    """Infer obvious relationships from parent links: siblings (share a parent)
    and grandparents (parent of a parent). Idempotent."""
    from collections import defaultdict
    rels = (await db.execute(select(PersonRelationship))).scalars().all()
    existing = {(r.from_person_id, r.to_person_id, r.rel_type) for r in rels}
    children = defaultdict(set)   # parent -> {children}
    parents = defaultdict(set)    # child -> {parents}
    for r in rels:
        # Treat parent/father/mother all as a parent→child link, and child/son/
        # daughter as the reverse, so derivation works whatever was entered.
        if r.rel_type in PARENT_TYPES:
            children[r.from_person_id].add(r.to_person_id)
            parents[r.to_person_id].add(r.from_person_id)
        elif r.rel_type in {"child", "son", "daughter"}:
            children[r.to_person_id].add(r.from_person_id)
            parents[r.from_person_id].add(r.to_person_id)

    def _has(a, b, t):
        return (a, b, t) in existing or (t not in DIRECTED and (b, a, t) in existing)

    new = []
    # siblings: any two children of the same parent
    for kids in children.values():
        kl = sorted(kids)
        for i in range(len(kl)):
            for j in range(i + 1, len(kl)):
                if not _has(kl[i], kl[j], "sibling"):
                    new.append(PersonRelationship(from_person_id=kl[i], to_person_id=kl[j], rel_type="sibling"))
                    existing.add((kl[i], kl[j], "sibling"))
    # grandparents: parent of a parent
    for child, ps in parents.items():
        for p in ps:
            for gp in parents.get(p, set()):
                if gp != child and not _has(gp, child, "grandparent"):
                    new.append(PersonRelationship(from_person_id=gp, to_person_id=child, rel_type="grandparent"))
                    existing.add((gp, child, "grandparent"))
    for r in new:
        db.add(r)
    await db.commit()
    return {"created": len(new)}


@router.post("")
async def create_relationship(body: RelCreate, db: AsyncSession = Depends(get_db)):
    if body.rel_type not in RELATION_TYPES:
        raise HTTPException(400, f"Unbekannter Beziehungstyp: {body.rel_type}")
    if body.from_person_id == body.to_person_id:
        raise HTTPException(400, "Eine Person kann nicht mit sich selbst verknüpft werden.")
    for pid in (body.from_person_id, body.to_person_id):
        if not await db.get(Person, pid):
            raise HTTPException(404, f"Person {pid} nicht gefunden")
    # de-dupe: for symmetric types, treat (a,b) == (b,a)
    directed = body.rel_type in DIRECTED
    existing = (await db.execute(select(PersonRelationship).where(
        PersonRelationship.rel_type == body.rel_type,
        or_(
            and_(PersonRelationship.from_person_id == body.from_person_id, PersonRelationship.to_person_id == body.to_person_id),
            and_(
                PersonRelationship.from_person_id == body.to_person_id,
                PersonRelationship.to_person_id == body.from_person_id,
            ) if not directed else and_(False),
        ),
    ))).scalars().first()
    if existing:
        return _edge(existing)
    rel = PersonRelationship(
        from_person_id=body.from_person_id, to_person_id=body.to_person_id,
        rel_type=body.rel_type, note=body.note,
    )
    db.add(rel)
    await db.commit()
    await db.refresh(rel)
    return _edge(rel)


@router.delete("/{rel_id}", status_code=204)
async def delete_relationship(rel_id: int, db: AsyncSession = Depends(get_db)):
    await db.execute(sql_delete(PersonRelationship).where(PersonRelationship.id == rel_id))
    await db.commit()


@router.get("/types")
async def relationship_types():
    """Grouped, labelled relationship types for the picker."""
    return [
        {"value": k, "label": v[0], "inverse_label": v[1], "category": v[2],
         "category_label": CATEGORY_LABELS.get(v[2], v[2]), "directed": v[3]}
        for k, v in RELATION_TYPES.items()
    ]
