import asyncio
import os
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


def _face_crop_path(face, photo, person_id: int = 0):
    """Path to a face crop. For a video face detected at a known frame_time, crop
    from THAT frame (not the 10%-mark thumbnail); else from the SSD thumbnail."""
    from app.services.face_crop import crop_face
    bbox = [face.bbox_x, face.bbox_y, face.bbox_w, face.bbox_h]
    if getattr(photo, "is_video", False) and face.frame_time is not None:
        # Extract the exact frame from the 1080p web MP4 on the SSD (fast seek) —
        # NEVER ffmpeg the 4K original on the spinning HDD (that was the slow/
        # "never loads" case). No web version yet → fall through to the SSD
        # thumbnail (instant, approximate frame) rather than hit the HDD.
        vsrc = photo.video_webm_path if (photo.video_webm_path and os.path.exists(photo.video_webm_path)) else None
        if vsrc:
            try:
                import io
                from PIL import Image
                from app.services.processing.thumbnails import extract_video_frame_bytes
                data = extract_video_frame_bytes(vsrc, float(face.frame_time))
                if data:
                    frame = Image.open(io.BytesIO(data))
                    return crop_face(photo.path, bbox, person_id, face.id, source_image=frame)
            except Exception:
                pass
    src = photo.thumb_large or photo.thumb_medium
    if not src and not getattr(photo, "is_video", False):
        src = photo.path  # last resort for an image without any thumbnail yet
    if not src:
        return None
    return crop_face(src, bbox, person_id, face.id)


@router.get("", response_model=List[PersonDetail])
async def list_people(include_hidden: bool = False, sort: str = "name",
                      db: AsyncSession = Depends(get_db)):
    """List persons with face- AND distinct-photo counts. `sort`:
    name | photos (most→least) | photos_asc | faces | recent.
    Counts come from two grouped queries (not N+1) so this stays fast."""
    q = select(Person)
    if not include_hidden:
        q = q.where(Person.is_hidden == False)  # noqa: E712
    persons = (await db.execute(q)).scalars().all()
    ids = [p.id for p in persons]
    faces, photos = {}, {}
    if ids:
        for pid, c in (await db.execute(
            select(Face.person_id, func.count()).where(Face.person_id.in_(ids)).group_by(Face.person_id)
        )).all():
            faces[pid] = c
        for pid, c in (await db.execute(
            select(Face.person_id, func.count(func.distinct(Face.photo_id)))
            .where(Face.person_id.in_(ids)).group_by(Face.person_id)
        )).all():
            photos[pid] = c
    result = [PersonDetail(**{k: getattr(p, k) for k in PersonOut.model_fields}, notes=p.notes,
                           face_count=faces.get(p.id, 0), photo_count=photos.get(p.id, 0))
              for p in persons]
    name_key = lambda r: (r.name or "￿").lower()  # unnamed sort last on ties
    if sort == "photos":
        result.sort(key=lambda r: (-r.photo_count, name_key(r)))
    elif sort == "photos_asc":
        result.sort(key=lambda r: (r.photo_count, name_key(r)))
    elif sort == "faces":
        result.sort(key=lambda r: (-r.face_count, name_key(r)))
    elif sort == "recent":
        result.sort(key=lambda r: r.created_at, reverse=True)
    else:
        result.sort(key=name_key)
    return result


@router.post("/warm-crops")
async def warm_crops(db: AsyncSession = Depends(get_db)):
    """Pre-generate (warm) the 256px face-crop cache for every face so the People
    page never triggers on-demand crops — the slow case being VIDEO faces (each
    uncached crop runs ffmpeg to pull the exact frame). Idempotent."""
    n = await db.scalar(select(func.count()).where(Face.is_ignored == False))  # noqa: E712
    from app.worker.tasks import warm_face_crops_task
    warm_face_crops_task.delay()
    return {"queued_faces": int(n or 0)}


@router.get("/crops-status")
async def crops_status(db: AsyncSession = Depends(get_db)):
    """Progress for the crop-cache warming: cached crop files vs. total faces."""
    import os
    from app.services.face_crop import _CACHE
    total = await db.scalar(select(func.count()).where(Face.is_ignored == False)) or 0  # noqa: E712
    try:
        cached = sum(1 for e in os.scandir(_CACHE) if e.name.endswith(".jpg"))
    except Exception:
        cached = 0
    return {"total_faces": int(total), "cached": int(cached)}


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
    # NOTE: person names are NOT written into files here. During the messy
    # detect → cluster → name phase that would write into thousands of files
    # prematurely. The user persists names explicitly via POST /people/write-faces
    # (the "In Dateien schreiben" button → write_faces_task) once the assignments
    # have settled — it writes MWG face regions (box + name) into file/sidecar.
    return person


@router.post("/write-faces")
async def write_faces_to_files(db: AsyncSession = Depends(get_db)):
    """Persist EVERY detected face as an MWG face region (box + name where known)
    into the files. Button-driven — run once the detect → cluster → name phase has
    settled. Unknown faces keep just their coordinates, so a future tool never has
    to re-run face DETECTION. Returns how many photos will be processed."""
    n_photos = await db.scalar(
        select(func.count(func.distinct(Face.photo_id))).where(Face.is_ignored == False)  # noqa: E712
    )
    from app.worker.tasks import write_faces_task
    write_faces_task.delay()
    return {"queued_photos": int(n_photos or 0)}


@router.post("/detect-faces-local")
async def detect_faces_local(db: AsyncSession = Depends(get_db)):
    """Run face detection on the SERVER (insightface, CPU) for every image still
    lacking a face pass — decoupled from the slow descriptions, so faces finish
    in parallel. Same model as the remote agent → compatible embeddings."""
    from sqlalchemy import exists as _exists
    from app.models.photo import Photo
    n = await db.scalar(select(func.count()).select_from(Photo).where(
        Photo.thumb_large.isnot(None), Photo.is_video == False,  # noqa: E712
        Photo.is_missing == False, Photo.faces_scanned == False,  # noqa: E712
        ~_exists().where(Face.photo_id == Photo.id),
    ))
    from app.worker.tasks import sweep_faces_local_task
    sweep_faces_local_task.delay()
    return {"queued_photos": int(n or 0)}


@router.post("/reembed-imported")
async def reembed_imported(db: AsyncSession = Depends(get_db)):
    """Recover ArcFace embeddings for faces imported from MWG regions (box only,
    no embedding) so they re-join clustering after a recovery/re-import."""
    n = await db.scalar(select(func.count()).select_from(Face).where(
        Face.detector == "imported", Face.embedding.is_(None)))
    from app.worker.tasks import reembed_imported_faces_task
    reembed_imported_faces_task.delay()
    return {"queued_faces": int(n or 0)}


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
        # Offload the (sync, possibly ffmpeg/PIL) crop work to a thread so one slow
        # crop never blocks the event loop / the other ~40 parallel crop requests.
        crop_path = await asyncio.to_thread(_face_crop_path, face, photo, person_id)
        if crop_path and os.path.exists(crop_path):
            return FileResponse(crop_path, media_type="image/jpeg")
        return None

    # Honour a profile face only for NAMED persons (a user likely picked it).
    # Auto-clustered unnamed persons get the most face-like crop instead of the
    # arbitrary first face — otherwise the tile shows a wall/scenery FP.
    if person.profile_face_id and (person.name or "").strip():
        pf = await db.get(Face, person.profile_face_id)
        # Only use it if it still belongs to this person (merge/reassign can leave
        # a stale profile_face_id pointing elsewhere).
        if pf and pf.person_id == person_id:
            res = await _try(pf)
            if res:
                return res

    # Rank by face-likeness: real faces are ~square (w/h 0.6–1.05); interlaced
    # FPs are tall/narrow. Prefer those, then highest confidence. Try a few in
    # case the top crop file isn't on disk yet.
    from sqlalchemy import case
    _ar = Face.bbox_w / func.nullif(Face.bbox_h, 0)
    _facelike = case((_ar.between(0.6, 1.05), 0), else_=1)
    candidates = (await db.execute(
        select(Face).where(Face.person_id == person_id)
        .order_by(_facelike.asc(), Face.confidence.desc().nullslast()).limit(5)
    )).scalars().all()
    for c in candidates:
        res = await _try(c)
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
async def person_faces(person_id: int, page: int = 1, limit: int = 120,
                       db: AsyncSession = Depends(get_db)):
    """List the faces assigned to a person — PAGINATED. A person can have
    thousands of faces (e.g. a child photographed for years); returning + rendering
    all of them as on-demand crops froze the page. Best faces first."""
    limit = max(1, min(limit, 500))
    total = await db.scalar(select(func.count()).select_from(Face).where(Face.person_id == person_id))
    rows = (await db.execute(
        select(Face.id, Face.photo_id, Face.confidence)
        .where(Face.person_id == person_id).order_by(Face.confidence.desc().nullslast())
        .offset((max(1, page) - 1) * limit).limit(limit)
    )).all()
    return {"total": total or 0, "page": page, "limit": limit,
            "items": [{"id": r[0], "photo_id": r[1], "confidence": r[2]} for r in rows]}


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
    return {"person_id": person.id}


@router.delete("/faces/{face_id}/unassign", status_code=204)
async def unassign_face(face_id: int, db: AsyncSession = Depends(get_db)):
    face = await db.get(Face, face_id)
    if not face:
        raise HTTPException(404)
    face.person_id = None
    await db.commit()


@router.get("/faces/unassigned")
async def unassigned_faces(page: int = 1, limit: int = Query(50, ge=1, le=500),
                           db: AsyncSession = Depends(get_db)):
    """Paginated — there can be thousands of loose faces; returning all of them as
    on-demand crops froze the page. Best-confidence first."""
    where = (Face.person_id == None, Face.is_ignored == False)  # noqa: E711,E712
    total = await db.scalar(select(func.count()).select_from(Face).where(*where))
    rows = (await db.execute(
        select(Face.id, Face.photo_id, Face.confidence).where(*where)
        .order_by(Face.confidence.desc().nullslast())
        .offset((max(1, page) - 1) * limit).limit(limit)
    )).all()
    return {"total": total or 0, "page": page, "limit": limit,
            "items": [{"id": r[0], "photo_id": r[1], "confidence": r[2]} for r in rows]}


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
    path = await asyncio.to_thread(_face_crop_path, face, photo, 0)
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
