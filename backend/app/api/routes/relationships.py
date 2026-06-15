"""Person relationships — family/social graph (Stammbaum)."""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, and_, delete as sql_delete
from pydantic import BaseModel

from app.core.database import get_db
from app.models.person import Person
from app.models.face import Face
from app.models.relationship import PersonRelationship, RelationType, DIRECTED, CATEGORY

router = APIRouter(prefix="/relationships", tags=["relationships"])


class RelCreate(BaseModel):
    from_person_id: int
    to_person_id: int
    rel_type: RelationType
    note: Optional[str] = None


def _edge(r: PersonRelationship) -> dict:
    return {
        "id": r.id, "from": r.from_person_id, "to": r.to_person_id,
        "type": r.rel_type.value, "category": CATEGORY[r.rel_type],
        "directed": r.rel_type in DIRECTED, "note": r.note,
    }


@router.get("/graph")
async def graph(db: AsyncSession = Depends(get_db)):
    """All persons (nodes) + relationships (edges) for the network view."""
    persons = (await db.execute(select(Person).order_by(Person.name))).scalars().all()
    counts = dict((await db.execute(
        select(Face.person_id, func.count()).where(Face.person_id.isnot(None)).group_by(Face.person_id)
    )).all())
    nodes = [{
        "id": p.id, "name": p.name or "Unbekannt", "named": bool((p.name or "").strip()),
        "face_count": counts.get(p.id, 0), "profile_face_id": p.profile_face_id,
    } for p in persons]
    rels = (await db.execute(select(PersonRelationship))).scalars().all()
    return {"nodes": nodes, "edges": [_edge(r) for r in rels]}


@router.get("/person/{person_id}")
async def for_person(person_id: int, db: AsyncSession = Depends(get_db)):
    rels = (await db.execute(
        select(PersonRelationship).where(
            or_(PersonRelationship.from_person_id == person_id, PersonRelationship.to_person_id == person_id)
        )
    )).scalars().all()
    return [_edge(r) for r in rels]


@router.post("")
async def create_relationship(body: RelCreate, db: AsyncSession = Depends(get_db)):
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
    return [{"value": t.value, "category": CATEGORY[t], "directed": t in DIRECTED} for t in RelationType]
