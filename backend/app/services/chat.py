"""Conversational assistant over the photo library.

Two modes (toggle: chat.provider):
  • gemini  → a tool-calling AGENT: it decides when to call `suche_fotos`,
    gets fused photo records (description + recognised people + tags + date/place)
    and reasons over them (so "person in the blue shirt" + recognised "Günter
    Nimtz" → it concludes they're the same person).
  • local   → simple RAG: retrieve top matches, hand the fused context to the
    local Qwen to answer (private, slower — the server has no GPU).

Grounded: the model is told to answer ONLY from the retrieved photos.
"""
import asyncio
import json
from datetime import date
from typing import List, Optional

import httpx
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.photo import Photo
from app.models.face import Face
from app.models.person import Person
from app.models.tag import Tag, PhotoTag
from app.services.photo_search import search_photos

SYSTEM = (
    "Du bist der Foto-Assistent von PhotoFlow und beantwortest Fragen zur privaten "
    "Foto-/Videosammlung des Nutzers auf Deutsch. Zu jedem Foto bekommst du: die "
    "visuelle Beschreibung (Personen oft anonym beschrieben), die per "
    "Gesichtserkennung ERKANNTEN Namen, Tags, Datum und Ort. Kombiniere diese: "
    "eine anonym beschriebene Person ist sehr wahrscheinlich eine der erkannten "
    "benannten Personen (z. B. „Person im blauen Hemd“ + erkannt „Günter Nimtz“ → "
    "die Person im blauen Hemd ist Günter Nimtz). Antworte ausschließlich anhand "
    "der gefundenen Fotos; gibt es keine Treffer, sage das ehrlich. Nenne relevante "
    "Fotos per #id. "
    "Nutze bei Fragen nach VIDEOS den Filter medientyp='video', bei Bildern/Fotos "
    "medientyp='bild'. Für 'wie viele …'-Fragen nutze das Werkzeug zaehle_fotos "
    "(exakte Anzahl) statt zu schätzen. Jahresangaben → jahr_von/jahr_bis."
)


async def _fused_records(db: AsyncSession, photos: List[Photo]) -> List[dict]:
    """Bundle description + recognised people + tags + date/place per photo so the
    LLM can reason over everything at once."""
    if not photos:
        return []
    ids = [p.id for p in photos]
    # recognised people per photo (named persons only)
    people: dict = {}
    for pid, name in (await db.execute(
        select(Face.photo_id, Person.name).join(Person, Person.id == Face.person_id)
        .where(Face.photo_id.in_(ids), Person.name.isnot(None))
    )).all():
        if name:
            people.setdefault(pid, set()).add(name)
    # tags per photo
    tags: dict = {}
    for pid, tname in (await db.execute(
        select(PhotoTag.photo_id, Tag.name).join(Tag, Tag.id == PhotoTag.tag_id)
        .where(PhotoTag.photo_id.in_(ids))
    )).all():
        tags.setdefault(pid, []).append(tname)
    out = []
    for p in photos:
        # Give the model the FULL rich description (we generate detailed, multi-
        # sentence descriptions — truncating to 400 chars threw most of it away).
        # 1500-char cap only bounds pathological outliers. Plus the user's own note
        # + title, which are strong, human-curated signals.
        desc = (p.description or "").strip()
        note = (getattr(p, "user_description", None) or "").strip()
        out.append({
            "id": p.id,
            "datum": str(p.taken_at)[:10] if p.taken_at else None,
            "ort": ", ".join([x for x in (p.city, p.country) if x]) or None,
            "titel": (getattr(p, "title", None) or "").strip() or None,
            "personen": sorted(people.get(p.id, [])) or None,
            "tags": (tags.get(p.id) or [])[:25] or None,
            "beschreibung": desc[:1500] or None,
            "notiz": note[:500] or None,
            "ist_video": bool(p.is_video),
        })
    return out


def _filter_conditions(medientyp: Optional[str], jahr_von: Optional[int], jahr_bis: Optional[int]):
    """SQLAlchemy conditions for the structured filters the chat tools expose.
    (No is_trashed here — search_photos adds its own; _count adds it explicitly.)"""
    conds = []
    mt = (medientyp or "").lower()
    if mt in ("video", "videos"):
        conds.append(Photo.is_video == True)   # noqa: E712
    elif mt in ("bild", "bilder", "foto", "fotos", "image", "images"):
        conds.append(Photo.is_video == False)  # noqa: E712
    if jahr_von:
        conds.append(Photo.taken_at >= date(int(jahr_von), 1, 1))
    if jahr_bis:
        conds.append(Photo.taken_at < date(int(jahr_bis) + 1, 1, 1))
    return conds


async def _retrieve(db: AsyncSession, query: str, settings: dict, limit: int = 20,
                    medientyp: Optional[str] = None, jahr_von: Optional[int] = None,
                    jahr_bis: Optional[int] = None) -> List[dict]:
    extra = _filter_conditions(medientyp, jahr_von, jahr_bis)
    photos = await search_photos(db, query or "", settings, limit=limit,
                                 extra_conditions=extra or None)
    return await _fused_records(db, photos)


async def _count(db: AsyncSession, medientyp: Optional[str], jahr_von: Optional[int],
                 jahr_bis: Optional[int], person: Optional[str]) -> dict:
    """Exact count for 'wie viele …' questions — structural filters, not top-K search."""
    conds = _filter_conditions(medientyp, jahr_von, jahr_bis) + [Photo.is_trashed == False]  # noqa: E712
    q = select(func.count(func.distinct(Photo.id))).select_from(Photo)
    if person and person.strip():
        q = (q.join(Face, Face.photo_id == Photo.id)
              .join(Person, Person.id == Face.person_id)
              .where(Person.name.ilike(f"%{person.strip()}%")))
    q = q.where(*conds)
    n = await db.scalar(q)
    return {"anzahl": int(n or 0), "medientyp": medientyp or "beide",
            "jahr_von": jahr_von, "jahr_bis": jahr_bis, "person": person}


async def _gemini_agent(message: str, history: list, settings: dict, db: AsyncSession) -> dict:
    key = (settings.get("ai.gemini.api_key") or "").strip()
    if not key:
        return {"answer": "Kein Gemini-API-Key hinterlegt (Einstellungen → KI).", "photo_ids": []}
    model = settings.get("ai.gemini.model", "gemini-2.5-flash")
    base = "https://generativelanguage.googleapis.com/v1beta"
    _filter_props = {
        "medientyp": {"type": "string", "enum": ["bild", "video", "beide"],
                      "description": "Nur Bilder, nur Videos, oder beide. WICHTIG: fragt der Nutzer nach Videos → 'video', nach Bildern/Fotos → 'bild'."},
        "jahr_von": {"type": "integer", "description": "frühestes Jahr (inkl.), z. B. 2018"},
        "jahr_bis": {"type": "integer", "description": "spätestes Jahr (inkl.), z. B. 2020"},
    }
    tool = {"function_declarations": [
        {
            "name": "suche_fotos",
            "description": "Durchsucht die Sammlung semantisch + nach Person/Ort/Tag und liefert passende "
                           "Medien mit Beschreibung, erkannten Personen, Tags, Datum, Ort. Mit Filtern für "
                           "Medientyp (Bild/Video) und Jahr.",
            "parameters": {"type": "object", "properties": {
                "suchbegriff": {"type": "string", "description": "Wonach gesucht wird, z. B. 'Günter im Garten', 'Strand'"},
                **_filter_props,
            }, "required": ["suchbegriff"]},
        },
        {
            "name": "zaehle_fotos",
            "description": "Liefert die EXAKTE Anzahl passender Medien (für 'wie viele …'-Fragen). "
                           "Filtert nach Medientyp, Jahr und optional Person.",
            "parameters": {"type": "object", "properties": {
                "person": {"type": "string", "description": "optionaler Personenname, z. B. 'Lea Marie Nimtz'"},
                **_filter_props,
            }},
        },
    ]}
    contents = []
    for h in (history or [])[-8:]:
        role = "user" if h.get("role") == "user" else "model"
        contents.append({"role": role, "parts": [{"text": h.get("content", "")}]})
    contents.append({"role": "user", "parts": [{"text": message}]})

    seen_ids: list = []
    async with httpx.AsyncClient(timeout=60) as client:
        for _ in range(5):  # allow a few tool round-trips
            payload = {
                "system_instruction": {"parts": [{"text": SYSTEM}]},
                "contents": contents,
                "tools": [tool],
            }
            r = None
            for attempt in range(4):  # Gemini 503/429 spikes are usually transient
                r = await client.post(f"{base}/models/{model}:generateContent",
                                      params={"key": key}, json=payload)
                if r.status_code in (429, 500, 503) and attempt < 3:
                    await asyncio.sleep(2 ** attempt)  # 1,2,4s backoff
                    continue
                break
            if r.status_code != 200:
                return {"answer": f"Gemini gerade nicht erreichbar ({r.status_code}). Bitte gleich nochmal versuchen.",
                        "photo_ids": seen_ids}
            cand = (r.json().get("candidates") or [{}])[0]
            parts = (cand.get("content") or {}).get("parts") or []
            calls = [p["functionCall"] for p in parts if "functionCall" in p]
            if calls:
                contents.append({"role": "model", "parts": parts})
                for c in calls:
                    args = c.get("args") or {}
                    if c.get("name") == "zaehle_fotos":
                        resp = await _count(db, args.get("medientyp"), args.get("jahr_von"),
                                            args.get("jahr_bis"), args.get("person"))
                        contents.append({"role": "user", "parts": [{"functionResponse": {
                            "name": c["name"], "response": resp}}]})
                    else:
                        recs = await _retrieve(db, args.get("suchbegriff", ""), settings,
                                               medientyp=args.get("medientyp"),
                                               jahr_von=args.get("jahr_von"), jahr_bis=args.get("jahr_bis"))
                        seen_ids.extend([rrec["id"] for rrec in recs])
                        contents.append({"role": "user", "parts": [{"functionResponse": {
                            "name": c["name"], "response": {"treffer": recs}}}]})
                continue
            text = " ".join(p["text"] for p in parts if "text" in p).strip()
            # de-dupe preserving order
            uniq = list(dict.fromkeys(seen_ids))
            return {"answer": text or "(keine Antwort)", "photo_ids": uniq}
    return {"answer": "Abgebrochen (zu viele Tool-Schritte).", "photo_ids": list(dict.fromkeys(seen_ids))}


async def _local_rag(message: str, settings: dict, db: AsyncSession) -> dict:
    recs = await _retrieve(db, message, settings)
    if not recs:
        return {"answer": "Dazu habe ich keine passenden Fotos gefunden.", "photo_ids": []}
    from app.services.ai.local_vlm import LocalVLMProvider
    ctx = json.dumps(recs, ensure_ascii=False, indent=0)
    prompt = (f"{SYSTEM}\n\nGefundene Fotos (JSON):\n{ctx}\n\nFrage: {message}\n\n"
              "Antworte knapp auf Deutsch, nur anhand dieser Fotos.")
    model = (settings.get("ai.local.model") or "qwen2.5-vl-3b")
    prov = LocalVLMProvider(model if model.startswith("qwen") else "qwen2.5-vl-3b")
    answer = await prov.generate_text(prompt, max_new_tokens=400)
    if not (answer or "").strip():
        # The server host has no GPU (local VLM disabled) → local chat text-gen
        # can't run here. Retrieval still worked, so surface the photos + steer to Gemini.
        return {"answer": "Der lokale Chat braucht ein GPU am Server (hier nicht vorhanden). "
                          "Stell den Chat-Assistenten auf Gemini um (Einstellungen → Chat-Assistent) "
                          "— die gefundenen Fotos siehst du unten.",
                "photo_ids": [r["id"] for r in recs]}
    return {"answer": answer, "photo_ids": [r["id"] for r in recs]}


async def chat(message: str, history: list, settings: dict, db: AsyncSession,
               provider: Optional[str] = None) -> dict:
    prov = (provider or settings.get("chat.provider") or "gemini").lower()
    if prov == "local":
        return await _local_rag(message, settings, db)
    return await _gemini_agent(message, history, settings, db)
