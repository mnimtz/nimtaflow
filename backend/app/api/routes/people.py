from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update, delete as sql_delete
from pydantic import BaseModel

from app.core.database import get_db
from app.core.auth_guard import current_user_optional
from app.models.person import Person
from app.models.face import Face
from app.schemas.person import PersonCreate, PersonUpdate, PersonOut, PersonDetail

router = APIRouter(prefix="/people", tags=["people"])


@router.get("", response_model=List[PersonDetail])
async def list_people(include_hidden: bool = False, db: AsyncSession = Depends(get_db)):
    q = select(Person).order_by(Person.name)
    if not include_hidden:
        q = q.where(Person.is_hidden == False)  # noqa: E712
    persons = (await db.execute(q)).scalars().all()
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
    fields = data.model_dump(exclude_unset=True)
    name_changed = "name" in fields and (fields["name"] or "").strip()
    for k, v in fields.items():
        setattr(person, k, v)
    await db.commit()
    await db.refresh(person)
    # Write the person's name into their photos (XMP:PersonInImage) for re-import.
    if name_changed:
        try:
            from app.worker.tasks import write_person_name_task
            write_person_name_task.delay(person_id)
        except Exception:
            pass
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


class MergeMultiRequest(BaseModel):
    target_id: int
    source_ids: List[int]
    keep_name: Optional[str] = None


@router.post("/merge-multi")
async def merge_multiple(body: MergeMultiRequest, db: AsyncSession = Depends(get_db)):
    """Merge several selected persons into one target (multiselect in the UI).
    All faces of every source move to target; the sources are deleted."""
    target = await db.get(Person, body.target_id)
    if not target:
        raise HTTPException(404, "Target person not found")
    sources = [sid for sid in body.source_ids if sid != body.target_id]
    if not sources:
        raise HTTPException(400, "No other persons to merge")

    moved = await db.scalar(
        select(func.count()).where(Face.person_id.in_(sources))
    ) or 0
    await db.execute(
        update(Face).where(Face.person_id.in_(sources)).values(person_id=body.target_id)
    )
    if body.keep_name:
        target.name = body.keep_name
    if not target.profile_face_id:
        # inherit a profile face from the first source that has one
        for s in await db.execute(select(Person).where(Person.id.in_(sources))):
            sp = s[0]
            if sp.profile_face_id:
                target.profile_face_id = sp.profile_face_id
                break
    await db.execute(sql_delete(Person).where(Person.id.in_(sources)))
    await db.commit()
    return {"ok": True, "faces_moved": moved, "merged": len(sources), "target_id": target.id}


# ── Hide / unhide ─────────────────────────────────────────────────────────────

@router.post("/{person_id}/hide")
async def set_person_hidden(person_id: int, hidden: bool = True, db: AsyncSession = Depends(get_db)):
    """Hide a person from the main People grid (Immich-style) without deleting
    them — their faces stay assigned, so re-clustering won't re-surface them."""
    person = await db.get(Person, person_id)
    if not person:
        raise HTTPException(404)
    person.is_hidden = hidden
    await db.commit()
    return {"ok": True, "is_hidden": hidden}


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
        # Crop from the (SSD-cached) large thumbnail, not the full original on the
        # HDD — bbox is relative (0-1) so it maps to any size; avoids a slow HEIC
        # decode per face on first load.
        src = photo.thumb_large or photo.thumb_medium or photo.path
        crop_path = crop_face(src, bbox, person_id, face.id)
        if crop_path and os.path.exists(crop_path):
            return FileResponse(crop_path, media_type="image/jpeg")
        return None

    if person.profile_face_id:
        pf = await db.get(Face, person.profile_face_id)
        # Only use the profile face if it still belongs to this person (a merge or
        # reassignment can leave a stale profile_face_id pointing elsewhere).
        if pf and pf.person_id == person_id:
            res = await _try(pf)
            if res:
                return res

    res = await _try((await db.execute(
        select(Face).where(Face.person_id == person_id).order_by(Face.confidence.desc().nullslast()).limit(1)
    )).scalar_one_or_none())
    if res:
        return res

    raise HTTPException(404, "No avatar available")


# ── Person photos ──────────────────────────────────────────────────────────────

@router.get("/{person_id}/photos", response_model=None)
async def person_photos(
    person_id: int,
    page: int = 1,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    _acc_user=Depends(current_user_optional),
):
    person = await db.get(Person, person_id)
    if not person:
        raise HTTPException(404)

    from app.models.photo import Photo
    from app.schemas.photo import PhotoBase
    from app.core.access import photo_conditions

    q = (
        select(Photo)
        .join(Face, Face.photo_id == Photo.id)
        .where(Face.person_id == person_id, Photo.is_trashed == False, *photo_conditions(_acc_user))
        .order_by(Photo.taken_at.desc())
        .offset((page - 1) * limit).limit(limit)
    )
    photos = (await db.execute(q)).scalars().all()
    total = await db.scalar(
        select(func.count(func.distinct(Photo.id)))
        .join(Face, Face.photo_id == Photo.id)
        .where(Face.person_id == person_id, Photo.is_trashed == False, *photo_conditions(_acc_user))
    )
    items = [PhotoBase.model_validate(p, from_attributes=True) for p in photos]
    return {"total": total or 0, "page": page, "limit": limit, "items": items}


@router.get("/{person_id}/faces")
async def person_faces(person_id: int, db: AsyncSession = Depends(get_db)):
    """List the individual faces assigned to a person (for the faces strip)."""
    rows = (await db.execute(
        select(Face.id, Face.photo_id, Face.confidence)
        .where(Face.person_id == person_id).order_by(Face.confidence.desc().nullslast())
    )).all()
    return [{"id": r[0], "photo_id": r[1], "confidence": r[2]} for r in rows]


# ── Face management ───────────────────────────────────────────────────────────

@router.post("/faces/{face_id}/assign/{person_id}")
async def assign_face(face_id: int, person_id: int, db: AsyncSession = Depends(get_db)):
    face = await db.get(Face, face_id)
    if not face:
        raise HTTPException(404, "Face not found")
    face.person_id = person_id
    face.is_ignored = False
    await db.commit()
    return {"ok": True}


class AssignManyRequest(BaseModel):
    face_ids: List[int]
    person_id: int


@router.post("/faces/assign-many")
async def assign_faces_many(body: AssignManyRequest, db: AsyncSession = Depends(get_db)):
    """Assign several selected faces to one existing person at once."""
    if not body.face_ids:
        return {"updated": 0}
    person = await db.get(Person, body.person_id)
    if not person:
        raise HTTPException(404, "Person not found")
    await db.execute(update(Face).where(Face.id.in_(body.face_ids))
                     .values(person_id=body.person_id, is_ignored=False))
    await db.commit()
    return {"updated": len(body.face_ids), "person_id": body.person_id}


class NewPersonManyRequest(BaseModel):
    face_ids: List[int]
    name: Optional[str] = None


@router.post("/faces/new-person-many")
async def new_person_from_faces(body: NewPersonManyRequest, db: AsyncSession = Depends(get_db)):
    """Create a new person from several selected faces (optionally named)."""
    if not body.face_ids:
        raise HTTPException(400, "No faces given")
    person = Person(name=(body.name or "").strip(), profile_face_id=body.face_ids[0])
    db.add(person)
    await db.flush()
    await db.execute(update(Face).where(Face.id.in_(body.face_ids))
                     .values(person_id=person.id, is_ignored=False))
    await db.commit()
    if (body.name or "").strip():
        try:
            from app.worker.tasks import write_person_name_task
            write_person_name_task.delay(person.id)
        except Exception:
            pass
    return {"person_id": person.id}


@router.delete("/faces/{face_id}/unassign", status_code=204)
async def unassign_face(face_id: int, db: AsyncSession = Depends(get_db)):
    face = await db.get(Face, face_id)
    if not face:
        raise HTTPException(404)
    face.person_id = None
    await db.commit()


@router.get("/faces/unassigned")
async def unassigned_faces(limit: int = Query(200, ge=1, le=1000), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(
        select(Face.id, Face.photo_id, Face.confidence)
        .where(Face.person_id == None, Face.is_ignored == False)  # noqa: E711,E712
        .order_by(Face.confidence.desc().nullslast())
        .limit(limit)
    )).all()
    return [{"id": r[0], "photo_id": r[1], "confidence": r[2]} for r in rows]


class FaceIdsRequest(BaseModel):
    face_ids: List[int]


@router.post("/faces/ignore")
async def ignore_faces(body: FaceIdsRequest, ignored: bool = True, db: AsyncSession = Depends(get_db)):
    """Bulk hide/ignore (or restore) faces — for the many strangers' faces you
    don't want to manage. Ignored faces drop out of the unassigned list and are
    skipped by clustering. Also unassigns them from any person."""
    if not body.face_ids:
        return {"updated": 0}
    values = {"is_ignored": ignored}
    if ignored:
        values["person_id"] = None
    await db.execute(update(Face).where(Face.id.in_(body.face_ids)).values(**values))
    await db.commit()
    return {"updated": len(body.face_ids), "ignored": ignored}


@router.get("/faces/ignored")
async def ignored_faces(limit: int = Query(500, ge=1, le=2000), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(
        select(Face.id, Face.photo_id, Face.confidence)
        .where(Face.is_ignored == True)  # noqa: E712
        .order_by(Face.id.desc()).limit(limit)
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
    src = photo.thumb_large or photo.thumb_medium or photo.path  # crop from SSD thumb, not HDD original
    path = crop_face(src, bbox, 0, face_id)
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
    try:
        from app.services.face_cluster import cluster_unassigned
        return await cluster_unassigned(db)
    except ImportError:
        raise HTTPException(500, "scikit-learn nicht verfügbar")
