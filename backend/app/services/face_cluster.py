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


async def cluster_unassigned(db: AsyncSession, grow_only: bool = False, suggest: bool = False) -> dict:
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
    threshold = float(s.get("face.clustering_threshold", "0.45") or 0.45)
    # min_cluster_size 2: seltene Personen mit nur 2 Fotos werden nun geclustert
    # (waren vorher bei min_size=3 als „isolate" verworfen → NIE Grow-Ziel, NIE
    # Suggestion-Ziel — daher schrumpfte Recall bei kleinen sozialen Kreisen).
    min_size = max(2, int(float(s.get("face.min_cluster_size", "2") or 2)))
    algo = str(s.get("face.cluster_algo", "hdbscan")).lower()
    engine = str(s.get("face.engine", "insightface")).lower()

    # Only cluster faces from the active engine — facenet (VGGFace2) and InsightFace
    # (ArcFace) embeddings live in incompatible spaces and must never be mixed.
    # Also gate on confidence: low-conf detections (blurry crops, round toys, ears)
    # have noisy embeddings that cluster spuriously into junk "persons". Real faces
    # average ~0.81; require >= 0.65 so weak detections stay loose, not clustered.
    # 0.65 filterte massenhaft borderline Faces raus (0.55–0.65 sind reale
    # Detektionen aus Seiten-/Profilansicht). Google Fotos akzeptiert auch
    # schwache Signale und clustert sie besser. 0.55 gibt uns 30–50 % mehr
    # Zuordnungspotenzial.
    cmin = float(s.get("face.cluster_min_confidence", "0.55") or 0.55)
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

    # CRITICAL: all heavy numpy/sklearn below runs via asyncio.to_thread so it does
    # NOT block the event loop. Holding the single asyncpg connection idle across a
    # multi-second SYNC matmul starved the protocol → the server closed the socket →
    # the next UPDATE raised ConnectionDoesNotExistError → the whole txn rolled back →
    # grow assigned nothing ("Clustern bewirkt nichts"). End the read txn first too,
    # so the connection isn't held idle-in-transaction during compute.
    import asyncio
    await db.commit()

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
    await db.commit()  # drop the read txn before the CPU-bound compute
    assigned = 0
    remaining_ids, remaining_idx = [], []
    if existing:
        E = _norm(np.array([e for _, e in existing], dtype="float32"))   # (M, D)
        Epids = np.array([pid for pid, _ in existing])
        eps_existing = eps + 0.05  # exemplar match → a little more slack than cluster
        #   eps, but still TRACKS the configured threshold (tighten/loosen both work).

        def _grow_compute():
            # Pure numpy (NO db) → safe to run in a worker thread. CHUNK the unassigned
            # faces: the full X @ E.T is (U × M) — for ~12k loose × ~60k assigned that
            # is a single ~3 GB float32 matrix that OOM-killed the worker. Per-chunk
            # it stays ~CH × M.
            from collections import defaultdict as _dd
            by_pid = _dd(list)  # person_id -> [face_id]   (bulk-update per person)
            rem_ids, rem_idx = [], []
            CH = 1000
            for c0 in range(0, len(ids), CH):
                Xc = X[c0:c0 + CH]                                        # (c, D)
                sims = Xc @ E.T                                           # (c, M)
                jbest = sims.argmax(axis=1)
                sbest = sims[np.arange(len(Xc)), jbest]
                for k in range(len(Xc)):
                    fid = ids[c0 + k]
                    if 1.0 - float(sbest[k]) < eps_existing:
                        by_pid[int(Epids[jbest[k]])].append(fid)
                    else:
                        rem_ids.append(fid); rem_idx.append(c0 + k)
            return by_pid, rem_ids, rem_idx

        by_pid, remaining_ids, remaining_idx = await asyncio.to_thread(_grow_compute)
        for pid, fids in by_pid.items():
            await db.execute(update(Face).where(Face.id.in_(fids)).values(person_id=pid))
            assigned += len(fids)
        # Persist grow IMMEDIATELY — independent of stage 2. A failure forming new
        # clusters must never roll back faces already matched to known people.
        await db.commit()
    else:
        remaining_ids, remaining_idx = list(ids), list(range(len(ids)))

    # ── Safe SUGGESTIONS (no assignment): for the loose faces just BELOW the confident
    #    assign cutoff, record suggested_person_id so the user can confirm them under
    #    "ähnliche Gesichter" → review. Never touches person_id, never merges people.
    suggested = 0
    if suggest and existing and remaining_idx:
        from collections import defaultdict as _dd2
        band = float(s.get("face.suggest_band", "0.13") or 0.13)  # how far below the cutoff still counts as "likely"

        def _suggest_compute():
            out = _dd2(list)  # person_id -> [face_id]
            CH = 1000
            for c0 in range(0, len(remaining_idx), CH):
                idxs = remaining_idx[c0:c0 + CH]
                Xc = X[idxs]
                sims = Xc @ E.T
                jbest = sims.argmax(axis=1)
                sbest = sims[np.arange(len(Xc)), jbest]
                for k in range(len(Xc)):
                    d = 1.0 - float(sbest[k])
                    if eps_existing <= d < eps_existing + band:   # just outside confident, still plausible
                        out[int(Epids[jbest[k]])].append(ids[idxs[k]])
            return out

        sugg = await asyncio.to_thread(_suggest_compute)
        for pid, fids in sugg.items():
            # only on still-free faces; (re)set the suggestion
            await db.execute(update(Face).where(
                Face.id.in_(fids), Face.person_id == None  # noqa: E711
            ).values(suggested_person_id=pid))
            suggested += len(fids)
        await db.commit()

    # Light auto-run: stop after growing existing people — skip the heavy HDBSCAN.
    if grow_only:
        return {"assigned_to_existing": assigned, "clustered": 0, "suggested": suggested,
                "new_persons": 0, "merged_clusters": 0, "unclustered": len(remaining_ids)}

    # 2) Cluster the rest into new (unnamed) persons.
    new_persons = 0
    clustered = 0
    if len(remaining_ids) >= min_size:
        Xr = X[remaining_idx]

        def _cluster_compute():
            # Pure sklearn (NO db) → run in a worker thread (same event-loop reason).
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
                        cluster_selection_method="eom", core_dist_n_jobs=2,
                    ).fit_predict(Xr)
                except Exception:
                    labels = None
            if labels is None:
                # min_samples controls noise sensitivity, NOT minimum cluster size.
                # Tying it to min_size (e.g. 3) dumped real but under-photographed
                # people into noise. Use 2 (a pair is enough to seed a cluster) and
                # enforce min_size as a post-hoc size filter below → far better recall.
                labels = DBSCAN(eps=eps, min_samples=2, metric="cosine", n_jobs=2).fit_predict(Xr)
            return labels

        labels = await asyncio.to_thread(_cluster_compute)
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
