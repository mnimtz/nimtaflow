from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.core.database import get_db
from app.models.person import Person
from app.models.face import Face
from app.schemas.person import PersonCreate, PersonUpdate, PersonOut, PersonDetail

router = APIRouter(prefix="/people", tags=["people"])


@router.get("", response_model=List[PersonOut])
async def list_people(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Person).order_by(Person.name))
    persons = result.scalars().all()
    return persons


@router.post("", response_model=PersonOut, status_code=201)
async def create_person(data: PersonCreate, db: AsyncSession = Depends(get_db)):
    person = Person(**data.model_dump())
    db.add(person)
    await db.commit()
    await db.refresh(person)
    return person


@router.get("/{person_id}", response_model=PersonDetail)
async def get_person(person_id: int, db: AsyncSession = Depends(get_db)):
    person = await db.get(Person, person_id)
    if not person:
        raise HTTPException(404)
    face_count = await db.scalar(select(func.count()).where(Face.person_id == person_id))
    return PersonDetail(**person.__dict__, face_count=face_count or 0)


@router.patch("/{person_id}", response_model=PersonOut)
async def update_person(person_id: int, data: PersonUpdate, db: AsyncSession = Depends(get_db)):
    person = await db.get(Person, person_id)
    if not person:
        raise HTTPException(404)
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(person, k, v)
    await db.commit()
    await db.refresh(person)
    return person


@router.delete("/{person_id}", status_code=204)
async def delete_person(person_id: int, db: AsyncSession = Depends(get_db)):
    person = await db.get(Person, person_id)
    if not person:
        raise HTTPException(404)
    await db.delete(person)
    await db.commit()


@router.post("/faces/{face_id}/assign/{person_id}")
async def assign_face(face_id: int, person_id: int, db: AsyncSession = Depends(get_db)):
    face = await db.get(Face, face_id)
    if not face:
        raise HTTPException(404, "Face not found")
    face.person_id = person_id
    await db.commit()
    return {"ok": True}


@router.get("/faces/unassigned")
async def unassigned_faces(limit: int = Query(50, ge=1, le=200), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Face).where(Face.person_id == None).limit(limit)
    )
    return result.scalars().all()
