"""Shared face-clustering logic.

Groups still-unassigned face embeddings into people:
  1. Assign each unassigned face to an EXISTING person whose centroid it is
     close to — so re-clustering grows known people instead of duplicating them.
  2. Cluster the remaining faces into new (unnamed) persons via DBSCAN (cosine).

Used by both the manual `/people/cluster` endpoint and the periodic
auto-cluster beat task, so the behaviour is identical either way.
"""
from collections import defaultdict

from sqlalchemy import select, update, delete as _del
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.person import Person
from app.models.face import Face


async def cluster_unassigned(db: AsyncSession) -> dict:
    from app.services.settings_loader import load_settings

    # remove orphaned auto-persons (empty name + no faces, e.g. after reprocess)
    await db.execute(_del(Person).where(
        Person.name == "",
        ~Person.id.in_(select(Face.person_id).where(Face.person_id.isnot(None))),
    ))
    await db.commit()

    s = await load_settings(db)
    threshold = float(s.get("face.clustering_threshold", "0.6") or 0.6)
    min_size = max(2, int(float(s.get("face.min_cluster_size", "2") or 2)))
    algo = str(s.get("face.cluster_algo", "dbscan")).lower()

    rows = (await db.execute(
        select(Face.id, Face.embedding).where(
            Face.person_id == None, Face.is_ignored == False, Face.embedding.isnot(None)  # noqa: E711,E712
        )
    )).all()
    if len(rows) < min_size:
        return {"clustered": 0, "new_persons": 0, "unclustered": len(rows), "assigned_to_existing": 0}

    import numpy as np
    from sklearn.cluster import DBSCAN

    def _norm(a):
        n = np.linalg.norm(a, axis=-1, keepdims=True)
        return a / np.clip(n, 1e-9, None)

    ids = [r[0] for r in rows]
    X = _norm(np.array([r[1] for r in rows], dtype="float32"))
    eps = max(0.05, 1.0 - threshold)

    # 1) Grow existing people.
    existing = (await db.execute(
        select(Face.person_id, Face.embedding).where(Face.person_id.isnot(None), Face.embedding.isnot(None))
    )).all()
    centroids = {}
    if existing:
        acc = defaultdict(list)
        for pid, emb in existing:
            acc[pid].append(emb)
        for pid, embs in acc.items():
            centroids[pid] = _norm(np.mean(_norm(np.array(embs, dtype="float32")), axis=0))

    assigned = 0
    remaining_ids, remaining_idx = [], []
    for i, fid in enumerate(ids):
        best_pid, best_dist = None, 1e9
        for pid, c in centroids.items():
            d = 1.0 - float(np.dot(X[i], c))
            if d < best_dist:
                best_pid, best_dist = pid, d
        if best_pid is not None and best_dist < eps:
            await db.execute(update(Face).where(Face.id == fid).values(person_id=best_pid))
            assigned += 1
        else:
            remaining_ids.append(fid); remaining_idx.append(i)

    # 2) Cluster the rest into new (unnamed) persons.
    new_persons = 0
    clustered = 0
    if len(remaining_ids) >= min_size:
        Xr = X[remaining_idx]
        labels = None
        if algo == "hdbscan":
            # HDBSCAN handles varying cluster densities (people with many vs few
            # photos) better than DBSCAN and needs no eps. Falls back if missing.
            try:
                import hdbscan
                labels = hdbscan.HDBSCAN(
                    min_cluster_size=min_size, metric="euclidean"
                ).fit_predict(Xr)  # vectors are L2-normalised → euclidean ≈ cosine
            except Exception:
                labels = None
        if labels is None:
            labels = DBSCAN(eps=eps, min_samples=min_size, metric="cosine").fit_predict(Xr)
        clusters: dict = {}
        for fid, lbl in zip(remaining_ids, labels):
            if lbl == -1:
                continue
            clusters.setdefault(int(lbl), []).append(fid)
        for _, face_ids in clusters.items():
            person = Person(name="", profile_face_id=face_ids[0])
            db.add(person)
            await db.flush()
            await db.execute(update(Face).where(Face.id.in_(face_ids)).values(person_id=person.id))
            new_persons += 1
            clustered += len(face_ids)
    await db.commit()
    return {"assigned_to_existing": assigned, "clustered": clustered,
            "new_persons": new_persons, "unclustered": len(rows) - assigned - clustered}
