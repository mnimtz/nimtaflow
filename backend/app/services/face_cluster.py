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


async def cluster_unassigned(db: AsyncSession, grow_only: bool = False) -> dict:
    # grow_only=True does ONLY Stage 1 (assign loose faces to EXISTING named people)
    # and skips the heavy HDBSCAN that forms new clusters. The periodic auto-run uses
    # this so it stays light (no CPU spike that starves the API); the manual "Clustern"
    # button runs the full thing.
    from app.services.settings_loader import load_settings

    # remove orphaned auto-persons (empty name + no faces, e.g. after reprocess)
    await db.execute(_del(Person).where(
        Person.name == "",
        ~Person.id.in_(select(Face.person_id).where(Face.person_id.isnot(None))),
    ))
    await db.commit()

    s = await load_settings(db)
    # 0.5 default is calibrated for InsightFace/ArcFace, whose same-person cosine
    # sims peak ~0.45–0.55 (much lower than facenet's). 0.6 (the old facenet value)
    # was so strict that grow assigned 0 — genuine matches never reached it.
    threshold = float(s.get("face.clustering_threshold", "0.5") or 0.5)
    min_size = max(2, int(float(s.get("face.min_cluster_size", "3") or 3)))
    algo = str(s.get("face.cluster_algo", "dbscan")).lower()
    engine = str(s.get("face.engine", "facenet")).lower()

    # Only cluster faces from the active engine — facenet (VGGFace2) and InsightFace
    # (ArcFace) embeddings live in incompatible spaces and must never be mixed.
    # Also gate on confidence: low-conf detections (blurry crops, round toys, ears)
    # have noisy embeddings that cluster spuriously into junk "persons". Real faces
    # average ~0.81; require >= 0.65 so weak detections stay loose, not clustered.
    cmin = float(s.get("face.cluster_min_confidence", "0.65") or 0.65)
    rows = (await db.execute(
        select(Face.id, Face.embedding).where(
            Face.person_id == None, Face.is_ignored == False, Face.embedding.isnot(None),  # noqa: E711,E712
            Face.detector == engine, Face.confidence >= cmin,
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

    # 1) Grow existing people — match each unassigned face to its NEAREST
    #    EXEMPLAR (closest single assigned face), not the person's mean embedding.
    #    A centroid blurs a person who varies a lot (e.g. a baby across ages/
    #    angles), so clear faces sat unassigned. Nearest-exemplar assigns a face
    #    if it's close to ANY confirmed face of the person — far more recall, and
    #    a tad looser eps (exemplar match is stronger evidence than a centroid).
    existing = (await db.execute(
        select(Face.person_id, Face.embedding).where(
            Face.person_id.isnot(None), Face.embedding.isnot(None), Face.detector == engine)
    )).all()
    assigned = 0
    remaining_ids, remaining_idx = [], []
    if existing:
        E = _norm(np.array([e for _, e in existing], dtype="float32"))   # (M, D)
        Epids = [pid for pid, _ in existing]
        sims = X @ E.T                                                    # (U, M) cosine sim
        eps_existing = eps + 0.05  # exemplar match → a little more slack than cluster
        #   eps, but still TRACKS the configured threshold (tighten/loosen both work)
        #   — default threshold 0.6 → eps 0.4 → 0.45, same as before.
        for i, fid in enumerate(ids):
            j = int(np.argmax(sims[i]))
            if 1.0 - float(sims[i, j]) < eps_existing:
                await db.execute(update(Face).where(Face.id == fid).values(person_id=Epids[j]))
                assigned += 1
            else:
                remaining_ids.append(fid); remaining_idx.append(i)
    else:
        remaining_ids, remaining_idx = list(ids), list(range(len(ids)))

    # Light auto-run: stop after growing existing people — skip the heavy HDBSCAN.
    if grow_only:
        await db.commit()
        return {"assigned_to_existing": assigned, "clustered": 0,
                "new_persons": 0, "merged_clusters": 0, "unclustered": len(remaining_ids)}

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
                # eps is a COSINE distance; HDBSCAN works in EUCLIDEAN here. On
                # L2-normalised vectors euclidean² = 2·(1−cos) = 2·cos_dist, so the
                # equivalent euclidean radius is sqrt(2·eps) — passing the raw cosine
                # eps made the selection radius ~2× too small (weak merging).
                labels = hdbscan.HDBSCAN(
                    min_cluster_size=min_size, metric="euclidean",
                    cluster_selection_epsilon=float(np.sqrt(2.0 * eps)),
                    cluster_selection_method="eom", core_dist_n_jobs=2,  # cap CPU → keep API responsive
                ).fit_predict(Xr)
            except Exception:
                labels = None
        if labels is None:
            # min_samples controls noise sensitivity, NOT minimum cluster size.
            # Tying it to min_size (e.g. 3) dumped real but under-photographed
            # people into noise. Use 2 (a pair is enough to seed a cluster) and
            # enforce min_size as a post-hoc size filter below → far better recall.
            labels = DBSCAN(eps=eps, min_samples=2, metric="cosine", n_jobs=2).fit_predict(Xr)
        clusters: dict = {}
        for fid, lbl in zip(remaining_ids, labels):
            if lbl == -1:
                continue
            clusters.setdefault(int(lbl), []).append(fid)
        for _, face_ids in clusters.items():
            if len(face_ids) < min_size:   # discard clusters below the min size
                continue
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
