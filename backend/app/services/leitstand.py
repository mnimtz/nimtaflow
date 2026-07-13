"""v1.559: Einheitlicher Leitstand-Endpoint.

Web + iOS zeigen exakt dieselben 6 Kacheln aus dieser einen Quelle. Keine
Divergenzen mehr wie „iOS zeigt X, Web zeigt Y". Alle Zahlen kommen aus
DB + Redis + Celery — zum selben Zeitpunkt gemessen.

Schema (stabil, nur additiv erweitern):

{
  "updated_at": ISO,
  "kacheln": {
    "descriptions": {
      "title": "Beschreibungen",
      "text": {"done": …, "total": …, "pct": …},
      "structured": {"done": …, "total": …, "pct": …, "rate_per_hour": …},
      "detail": "kurzer Erklärungstext"
    },
    "videos": {
      "title": "Videos",
      "transcode": {"done": …, "total": …, "pct": …},
      "description": {"done": …, "total": …, "pct": …},
      "failed": …,
      "in_gemini_queue": …
    },
    "metadata": {
      "title": "Metadaten auf Foto-Platte",
      "sidecar": {"done": …, "total": …, "pct": …},
      "missing": …,          # Anzahl fehlender Sidecars, für Fix-Button
      "action_label": "…"    # Klartext-Button-Text
    },
    "people": {
      "title": "Personen",
      "named": …,             # benannte Personen (name != '')
      "faces_assigned": …,
      "faces_unassigned": …,
      "faces_suggestions": …
    },
    "reingest": {
      "title": "Reingest-Fortschritt",
      "pending": …,           # aktuell status=pending
      "in_batch": …,          # gesamter aktueller Batch (Anzahl noch offen)
      "done_last_hour": …,    # letzte Stunde neu strukturiert
      "eta_hours": …
    },
    "workers": [
      {"name": "m3-describe", "status": "aktiv|idle|offline",
       "rate_per_hour": …, "avg_seconds": …, "last_job_seconds": …}
    ]
  }
}
"""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.photo import Photo, PhotoStatus
from app.models.face import Face
from app.models.person import Person


async def _count(db: AsyncSession, *conds) -> int:
    return int(await db.scalar(
        select(func.count()).select_from(Photo).where(Photo.is_trashed == False, *conds)  # noqa: E712
    ) or 0)


async def build_leitstand(db: AsyncSession) -> dict:
    from app.core.config import get_settings as _gs
    import redis.asyncio as _aior
    import asyncio as _asyncio

    # ── DB-Zählungen (parallel) ───────────────────────────────────────────────
    async def _photos_totals():
        row = (await db.execute(
            select(
                func.count(Photo.id).filter(Photo.is_trashed == False),                                             # noqa: E712
                func.count(Photo.id).filter(Photo.is_video == False, Photo.is_trashed == False),                    # noqa: E712
                func.count(Photo.id).filter(Photo.is_video == True, Photo.is_trashed == False),                     # noqa: E712
                func.count(Photo.description).filter(Photo.is_trashed == False),
                func.count(Photo.id).filter(
                    Photo.structured_desc.has_key("style"),                                                          # noqa: E501
                    Photo.is_trashed == False),
                func.count(Photo.id).filter(
                    Photo.xmp_sidecar_written.is_(True), Photo.is_trashed == False),
                func.count(Photo.id).filter(
                    Photo.is_video == True, Photo.web_mp4_1080_at.isnot(None),                                       # noqa: E712
                    Photo.is_trashed == False),
                func.count(Photo.id).filter(
                    Photo.is_video == True, Photo.description.isnot(None), Photo.is_trashed == False),               # noqa: E712
                func.count(Photo.id).filter(
                    Photo.is_video == True, Photo.ai_error == True, Photo.is_trashed == False),                     # noqa: E712
                func.count(Photo.id).filter(
                    Photo.status == PhotoStatus.pending, Photo.is_video == False, Photo.is_trashed == False),        # noqa: E712
                func.count(Photo.id).filter(
                    Photo.structured_desc.is_(None), Photo.is_video == False,                                        # noqa: E712
                    Photo.is_trashed == False, Photo.is_missing == False),                                           # noqa: E712
                func.count(Photo.id).filter(
                    Photo.description.is_(None), Photo.is_trashed == False),
            )
        )).one()
        return row
    async def _people_stats():
        named = int(await db.scalar(select(func.count()).select_from(Person).where(Person.name != "")) or 0)
        assigned = int(await db.scalar(select(func.count()).select_from(Face).where(Face.person_id.isnot(None))) or 0)
        unassigned = int(await db.scalar(select(func.count()).select_from(Face).where(
            Face.person_id.is_(None), Face.is_ignored == False)) or 0)  # noqa: E712
        sugg = int(await db.scalar(select(func.count()).select_from(Face).where(
            Face.person_id.is_(None), Face.suggested_person_id.isnot(None))) or 0)
        return named, assigned, unassigned, sugg
    async def _structured_last_hour():
        # v1.556-Vollschema-Fotos die in der letzten Stunde processed wurden
        n = int(await db.scalar(
            select(func.count()).select_from(Photo).where(
                Photo.structured_desc.has_key("style"),                                                              # noqa: E501
                Photo.processed_at > func.now() - func.make_interval(0, 0, 0, 0, 1))                                 # noqa
        ) or 0)
        return n

    totals, people, per_hour = await _asyncio.gather(
        _photos_totals(), _people_stats(), _structured_last_hour()
    )
    (total, fotos, videos, mit_desc, mit_v556, mit_sidecar,
     v_transcoded, v_beschrieben, v_ai_error, status_pending, ohne_v556,
     ohne_desc) = totals
    (named, faces_assigned, faces_unassigned, faces_sugg) = people
    total = int(total or 0); fotos = int(fotos or 0); videos = int(videos or 0)

    def _pct(a, b):
        return round(100.0 * a / b, 1) if b else 0.0

    # ── Redis / Worker ────────────────────────────────────────────────────────
    queues: dict = {}
    worker_stats: list = []
    try:
        rc = _aior.from_url(_gs().redis_url)
        for q in ("cpu", "gpu", "scan", "video"):
            queues[q] = int(await rc.llen(q))
        keys = []
        async for k in rc.scan_iter("remote:worker:*"):
            keys.append(k.decode() if isinstance(k, (bytes, bytearray)) else k)
        now_ts = int(datetime.now(timezone.utc).timestamp())
        for k in sorted(keys):
            name = k.split(":", 2)[-1]
            ts_raw = await rc.get(k)
            try:
                ts_i = int(ts_raw)
            except Exception:
                ts_i = 0
            age = now_ts - ts_i if ts_i else 9999
            stats = await rc.hgetall(f"remote:wstats:{name}") or {}
            def _s(k_):
                v = stats.get(k_) if isinstance(stats, dict) else None
                if v is None:
                    v = stats.get(k_.encode()) if isinstance(stats, dict) else None
                return v
            avg_str = _s("avg")
            try:
                avg = float(avg_str) if avg_str is not None else 0.0
            except Exception:
                avg = 0.0
            rate_per_hour = int(3600.0 / avg) if avg > 0.5 else 0
            worker_stats.append({
                "name": name,
                "status": "aktiv" if age < 60 else ("idle" if age < 300 else "offline"),
                "letzte_arbeit_vor_sekunden": age if age < 9999 else None,
                "durchschnitt_sek": round(avg, 1),
                "rate_pro_stunde": rate_per_hour,
            })
        await rc.aclose()
    except Exception as _e:
        queues = {"fehler": str(_e)[:80]}

    # ── Kacheln bauen ─────────────────────────────────────────────────────────
    kacheln = {
        "descriptions": {
            "title": "Beschreibungen",
            "text":       {"done": mit_desc,  "total": total, "pct": _pct(mit_desc, total)},
            "structured": {"done": mit_v556,  "total": fotos, "pct": _pct(mit_v556, fotos),
                           "rate_pro_stunde": per_hour},
            "ohne_beschreibung": ohne_desc,
            "detail": ("Freitext-Beschreibung sowie strukturiertes JSON (28 Felder) "
                       "für die intelligente Chat-Suche."),
        },
        "videos": {
            "title": "Videos",
            "transcode":   {"done": v_transcoded, "total": videos, "pct": _pct(v_transcoded, videos)},
            "beschreibung":{"done": v_beschrieben, "total": videos, "pct": _pct(v_beschrieben, videos)},
            "fehler":      int(v_ai_error or 0),
        },
        "metadata": {
            "title": "Metadaten auf Foto-Platte (XMP-Sidecars)",
            "sidecar":     {"done": mit_sidecar, "total": total, "pct": _pct(mit_sidecar, total)},
            "fehlend":     max(0, total - int(mit_sidecar or 0)),
            "action_label":"Fehlende Sidecars nachschreiben",
            "action_task": "backfill_xmp",
            "detail": ("Jede Beschreibung + Face-Regionen werden zusätzlich als .xmp neben "
                       "das Foto geschrieben — überlebt DB-Verlust."),
        },
        "people": {
            "title": "Personen",
            "namen":            named,
            "faces_zugeordnet": faces_assigned,
            "faces_offen":      faces_unassigned,
            "faces_vorschlaege": faces_sugg,
        },
        "reingest": {
            "title": "Reingest-Fortschritt (2017+)",
            "pending":     status_pending,
            "in_batch":    ohne_v556,
            "done_last_hour": per_hour,
            "eta_stunden": round(ohne_v556 / max(1, per_hour), 1) if per_hour else None,
        },
        "workers": worker_stats,
        "warteschlangen": queues,
    }
    return {
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "kacheln": kacheln,
    }
