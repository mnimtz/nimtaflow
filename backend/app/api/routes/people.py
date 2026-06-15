from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update
from pydantic import BaseModel

from app.core.database import get_db
from app.models.person import Person
from app.models.face import Face
from app.schemas.person import PersonCreate, PersonUpdate, PersonOut, PersonDetail

router = APIRouter(prefix="/people", tags=["people"])


@router.get("", response_model=List[PersonDetail])
async def list_people(db: AsyncSession = Depends(get_db)):
    persons = (await db.execute(select(Person).order_by(Person.name))).scalars().all()
    result = []
    for p in persons:
        face_count = await db.scalar(select(func.count()).where(Face.person_id == p.id))
        result.append(PersonDetail(**{k: getattr(p, k) for k in PersonOut.model_fields}, notes=p.notes, face_count=face_count or 0))
    return result


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
    # Unassign all faces before deleting
    await db.execute(update(Face).where(Face.person_id == person_id).values(person_id=None))
    await db.delete(person)
    await db.commit()


# ── Merge persons ─────────────────────────────────────────────────────────────

class MergeRequest(BaseModel):
    source_id: int
    target_id: int
    keep_name: Optional[str] = None  # if set, override target name after merge


@router.post("/merge")
async def merge_persons(body: MergeRequest, db: AsyncSession = Depends(get_db)):
    """Merge source into target: all faces of source are reassigned to target, source is deleted."""
    source = await db.get(Person, body.source_id)
    target = await db.get(Person, body.target_id)
    if not source or not target:
        raise HTTPException(404, "Person not found")
    if source.id == target.id:
        raise HTTPException(400, "Cannot merge a person with themselves")

    moved = await db.scalar(
        select(func.count()).where(Face.person_id == body.source_id)
    ) or 0

    await db.execute(
        update(Face).where(Face.person_id == body.source_id).values(person_id=body.target_id)
    )

    if body.keep_name:
        target.name = body.keep_name

    # Prefer source profile face if target has none
    if not target.profile_face_id and source.profile_face_id:
        target.profile_face_id = source.profile_face_id

    await db.delete(source)
    await db.commit()
    return {"ok": True, "faces_moved": moved, "target_id": target.id}


# ── Profile / display image ───────────────────────────────────────────────────

@router.post("/{person_id}/profile-face/{face_id}")
async def set_profile_face(person_id: int, face_id: int, db: AsyncSession = Depends(get_db)):
    """Set which face crop to use as the person's display avatar."""
    person = await db.get(Person, person_id)
    face = await db.get(Face, face_id)
    if not person or not face:
        raise HTTPException(404)
    if face.person_id != person_id:
        raise HTTPException(400, "Face does not belong to this person")
    person.profile_face_id = face_id
    await db.commit()
    return {"ok": True, "profile_face_id": face_id}


@router.get("/{person_id}/avatar")
async def person_avatar(person_id: int, db: AsyncSession = Depends(get_db)):
    """Return the face crop image for the person's profile."""
    import os
    person = await db.get(Person, person_id)
    if not person:
        raise HTTPException(404)

    from app.models.photo import Photo
    from app.services.face_crop import crop_face

    async def _try(face: Optional[Face]):
        if not face:
            return None
        photo = await db.get(Photo, face.photo_id)
        if not photo:
            return None
        bbox = [face.bbox_x, face.bbox_y, face.bbox_w, face.bbox_h]
        crop_path = crop_face(photo.path, bbox, person_id, face.id)
        if crop_path and os.path.exists(crop_path):
            return FileResponse(crop_path, media_type="image/jpeg")
        return None

    if person.profile_face_id:
        res = await _try(await db.get(Face, person.profile_face_id))
        if res:
            return res

    res = await _try((await db.execute(
        select(Face).where(Face.person_id == person_id).limit(1)
    )).scalar_one_or_none())
    if res:
        return res

    raise HTTPException(404, "No avatar available")


# ── Person photos ──────────────────────────────────────────────────────────────

@router.get("/{person_id}/photos")
async def person_photos(
    person_id: int,
    page: int = 1,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    person = await db.get(Person, person_id)
    if not person:
        raise HTTPException(404)

    from app.models.photo import Photo
    from app.schemas.photo import PhotoBase

    q = (
        select(Photo)
        .join(Face, Face.photo_id == Photo.id)
        .where(Face.person_id == person_id, Photo.is_trashed == False)
        .order_by(Photo.taken_at.desc())
        .offset((page - 1) * limit).limit(limit)
    )
    photos = (await db.execute(q)).scalars().all()
    total = await db.scalar(
        select(func.count(func.distinct(Photo.id)))
        .join(Face, Face.photo_id == Photo.id)
        .where(Face.person_id == person_id, Photo.is_trashed == False)
    )
    return {"total": total or 0, "page": page, "limit": limit, "items": photos}


# ── Face management ───────────────────────────────────────────────────────────

@router.post("/faces/{face_id}/assign/{person_id}")
async def assign_face(face_id: int, person_id: int, db: AsyncSession = Depends(get_db)):
    face = await db.get(Face, face_id)
    if not face:
        raise HTTPException(404, "Face not found")
    face.person_id = person_id
    await db.commit()
    return {"ok": True}


@router.delete("/faces/{face_id}/unassign", status_code=204)
async def unassign_face(face_id: int, db: AsyncSession = Depends(get_db)):
    face = await db.get(Face, face_id)
    if not face:
        raise HTTPException(404)
    face.person_id = None
    await db.commit()


@router.get("/faces/unassigned")
async def unassigned_faces(limit: int = Query(100, ge=1, le=500), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(
        select(Face.id, Face.photo_id, Face.confidence).where(Face.person_id == None).limit(limit)
    )).all()
    return [{"id": r[0], "photo_id": r[1], "confidence": r[2]} for r in rows]


@router.get("/faces/{face_id}/crop")
async def face_crop_image(face_id: int, db: AsyncSession = Depends(get_db)):
    import os
    from app.models.photo import Photo
    from app.services.face_crop import crop_face
    face = await db.get(Face, face_id)
    if not face:
        raise HTTPException(404)
    photo = await db.get(Photo, face.photo_id)
    if not photo:
        raise HTTPException(404)
    bbox = [face.bbox_x, face.bbox_y, face.bbox_w, face.bbox_h]
    path = crop_face(photo.path, bbox, 0, face_id)
    if path and os.path.exists(path):
        return FileResponse(path, media_type="image/jpeg")
    raise HTTPException(404, "crop failed")


@router.post("/faces/{face_id}/new-person")
async def face_to_new_person(face_id: int, db: AsyncSession = Depends(get_db)):
    face = await db.get(Face, face_id)
    if not face:
        raise HTTPException(404)
    person = Person(name="", profile_face_id=face_id)
    db.add(person)
    await db.flush()
    face.person_id = person.id
    await db.commit()
    return {"person_id": person.id}


@router.post("/cluster")
async def cluster_faces(db: AsyncSession = Depends(get_db)):
    """Group still-unassigned face embeddings into people via DBSCAN (cosine).
    Each new cluster becomes an unnamed Person (rename/merge in the UI). Faces
    that don't cluster (noise) stay unassigned (= 'Gesichter'/unbekannt).
    Already-assigned faces are left untouched (preserves manual work)."""
    from app.services.settings_loader import load_settings
    from sqlalchemy import delete as _del
    # remove orphaned auto-persons (empty name + no faces, e.g. after reprocess)
    await db.execute(_del(Person).where(
        Person.name == "",
        ~Person.id.in_(select(Face.person_id).where(Face.person_id.isnot(None)))
    ))
    await db.commit()

    s = await load_settings(db)
    threshold = float(s.get("face.clustering_threshold", "0.6") or 0.6)
    min_size = max(2, int(float(s.get("face.min_cluster_size", "2") or 2)))

    rows = (await db.execute(
        select(Face.id, Face.embedding).where(Face.person_id == None, Face.embedding.isnot(None))
    )).all()
    if len(rows) < min_size:
        return {"clustered": 0, "new_persons": 0, "unclustered": len(rows)}

    try:
        import numpy as np
        from sklearn.cluster import DBSCAN
    except Exception:
        raise HTTPException(500, "scikit-learn nicht verfügbar")

    ids = [r[0] for r in rows]
    X = np.array([r[1] for r in rows], dtype="float32")
    # cosine distance; eps = 1 - similarity threshold
    labels = DBSCAN(eps=max(0.05, 1.0 - threshold), min_samples=min_size, metric="cosine").fit_predict(X)

    clusters: dict = {}
    for fid, lbl in zip(ids, labels):
        if lbl == -1:
            continue
        clusters.setdefault(int(lbl), []).append(fid)

    new_persons = 0
    clustered = 0
    for _, face_ids in clusters.items():
        person = Person(name="", profile_face_id=face_ids[0])
        db.add(person)
        await db.flush()
        await db.execute(update(Face).where(Face.id.in_(face_ids)).values(person_id=person.id))
        new_persons += 1
        clustered += len(face_ids)
    await db.commit()
    return {"clustered": clustered, "new_persons": new_persons, "unclustered": len(rows) - clustered}
