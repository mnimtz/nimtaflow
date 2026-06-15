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


async def consolidate_persons(db: AsyncSession, merge_eps: float) -> int:
    """Merge person-clusters whose face centroids are very close — this folds the
    fragments clustering inevitably produces (same person split across several
    groups) into one, so the user doesn't have to merge them by hand.

    Safety: two DIFFERENT named persons are NEVER merged (protects manual naming);
    only unnamed↔unnamed and unnamed↔named merges happen. Named persons act as
    the surviving anchor.
    """
    import numpy as np

    def _norm(a):
        n = np.linalg.norm(a, axis=-1, keepdims=True)
        return a / np.clip(n, 1e-9, None)

    rows = (await db.execute(
        select(Face.person_id, Face.embedding).where(Face.person_id.isnot(None), Face.embedding.isnot(None))
    )).all()
    if not rows:
        return 0
    acc = defaultdict(list)
    for pid, emb in rows:
        acc[pid].append(emb)
    pids = list(acc.keys())
    if len(pids) < 2:
        return 0
    cents = {pid: _norm(np.mean(_norm(np.array(e, dtype="float32")), axis=0)) for pid, e in acc.items()}
    names = dict((await db.execute(select(Person.id, Person.name).where(Person.id.in_(pids)))).all())
    named = {p for p in pids if (names.get(p) or "").strip()}

    parent = {p: p for p in pids}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra == rb:
            return
        a_named, b_named = ra in named, rb in named
        if a_named and not b_named:
            parent[rb] = ra
        elif b_named and not a_named:
            parent[ra] = rb
        else:
            keep, drop = (ra, rb) if ra < rb else (rb, ra)
            parent[drop] = keep

    # Persons the user named identically are clearly the same person → merge.
    byname = defaultdict(list)
    for p in pids:
        nm = (names.get(p) or "").strip().lower()
        if nm:
            byname[nm].append(p)
    for grp in byname.values():
        for k in range(1, len(grp)):
            union(grp[0], grp[k])

    arr = np.stack([cents[p] for p in pids])
    n = len(pids)
    for i in range(n):
        for j in range(i + 1, n):
            if pids[i] in named and pids[j] in named:
                continue  # never merge two distinct named people
            if 1.0 - float(np.dot(arr[i], arr[j])) < merge_eps:
                union(pids[i], pids[j])

    groups = defaultdict(list)
    for p in pids:
        groups[find(p)].append(p)
    merged = 0
    for root, members in groups.items():
        others = [m for m in members if m != root]
        if not others:
            continue
        await db.execute(update(Face).where(Face.person_id.in_(others)).values(person_id=root))
        await db.execute(_del(Person).where(Person.id.in_(others)))
        merged += len(others)
    if merged:
        await db.commit()
    return merged


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
    engine = str(s.get("face.engine", "facenet")).lower()

    # Only cluster faces from the active engine — facenet (VGGFace2) and InsightFace
    # (ArcFace) embeddings live in incompatible spaces and must never be mixed.
    rows = (await db.execute(
        select(Face.id, Face.embedding).where(
            Face.person_id == None, Face.is_ignored == False, Face.embedding.isnot(None),  # noqa: E711,E712
            Face.detector == engine,
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
        select(Face.person_id, Face.embedding).where(
            Face.person_id.isnot(None), Face.embedding.isnot(None), Face.detector == engine)
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
                    min_cluster_size=min_size, metric="euclidean",
                    # merge micro-clusters that sit within the same radius → fewer fragments
                    cluster_selection_epsilon=float(eps), cluster_selection_method="eom",
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
    # Consolidate fragments (same person split across clusters) automatically.
    merge_thr = float(s.get("face.merge_threshold", "0.5") or 0.5)
    merged = await consolidate_persons(db, max(0.05, 1.0 - merge_thr))
    return {"assigned_to_existing": assigned, "clustered": clustered,
            "new_persons": new_persons, "merged_clusters": merged,
            "unclustered": len(rows) - assigned - clustered}
