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
import base64
import json
import os
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
    "(exakte Anzahl) statt zu schätzen. Jahresangaben → jahr_von/jahr_bis. "
    "WICHTIG zu Personen: Enthält die Frage einen NAMEN (z. B. 'Lea'), setze immer "
    "den Parameter person='Lea' (schränkt auf Fotos MIT Lea ein) und nutze den "
    "suchbegriff nur für den Inhalt (z. B. 'Lea traurig' → person='Lea', "
    "suchbegriff='traurig weinen weint'; 'Lea am Strand' → person='Lea', "
    "suchbegriff='Strand'). "
    "Bei ZWEI Personen gemeinsam ('X mit Y', 'ich und meine Tochter', 'Lea und Anja "
    "zusammen') setze person UND person2 (beide müssen auf dem Foto sein). 'ich/mich/mir' "
    "= dein eigener Name aus der Identität. "
    "Bei ORTSANGABEN ('in der Türkei', 'in Köln', 'am Gardasee') setze IMMER den Parameter "
    "ort (Land, Stadt ODER Region; für Länder den deutschen Namen, z. B. ort='Türkei') und "
    "lass den suchbegriff dann leer oder knapp — der Ortsfilter findet ALLE Treffer dort, "
    "nicht nur die textlich ähnlichsten. "
    "Zu DATUM/EREIGNISSEN: Für konkrete Anlässe rechne den Zeitraum selbst aus und "
    "nutze datum_von/datum_bis (YYYY-MM-DD), z. B. 'Lea an Ostern 2022' → person='Lea', "
    "datum_von='2022-04-15', datum_bis='2022-04-18'. "
    "Zu 'WANN …'-Fragen (z. B. 'wann lernte Lea laufen'): suche mit person + passendem "
    "suchbegriff ('erste Schritte laufen lernen krabbeln'), schau dir die DATEN der "
    "Treffer an und nenne das früheste passende Datum als Antwort (Monat/Jahr). "
    "Für 'wann habe ich X das erste Mal getroffen/gesehen', 'seit wann kenne ich X', "
    "'wann zuletzt …' nutze IMMER das Werkzeug zeitliche_eckdaten (person=X) — es liefert "
    "das wirklich früheste/späteste Foto-Datum (datumssortiert). Geht es um GEMEINSAME "
    "Fotos mit dir, setze zusätzlich person2=<dein eigener Name aus der Identität>. "
    "Nenne dann erstes_datum bzw. letztes_datum als Antwort und das zugehörige Foto per #id. "
    "Du kannst auch HANDELN: Möchte der Nutzer ein Album anlegen, nutze "
    "album_erstellen; sollen Fotos favorisiert werden, nutze als_favorit_markieren. "
    "Bestätige danach kurz, was du getan hast (Albumname + Anzahl)."
)


async def _identity_context(db: AsyncSession, settings: dict, user=None) -> str:
    """Tell the assistant WHO the user is and their relations, so 'meine Frau' /
    'mein Sohn' resolve instantly instead of 'wer ist deine Frau?'. Prefers the
    LOGGED-IN user's linked person (access_config.person_id or User.person_id) so
    multi-user installs answer per-user; falls back to the global
    relationships.self_person_id."""
    sid = None
    if user is not None:
        sid = (getattr(user, "access_config", None) or {}).get("person_id") if getattr(user, "access_config", None) else None
        sid = sid or getattr(user, "person_id", None)
    try:
        sid = int(sid if sid is not None else settings.get("relationships.self_person_id"))
    except (TypeError, ValueError):
        return ""
    from sqlalchemy import or_
    from app.models.relationship import PersonRelationship, LABEL, INVERSE_LABEL
    me = await db.get(Person, sid)
    if not me:
        return ""
    rels = (await db.execute(select(PersonRelationship).where(or_(
        PersonRelationship.from_person_id == sid,
        PersonRelationship.to_person_id == sid,
    )))).scalars().all()
    pairs = []
    for r in rels:
        if r.to_person_id == sid:
            pairs.append((LABEL.get(r.rel_type, ""), r.from_person_id))
        else:
            pairs.append((INVERSE_LABEL.get(r.rel_type, ""), r.to_person_id))
    ids = {oid for _, oid in pairs}
    names = {}
    if ids:
        names = {i: n for i, n in (await db.execute(
            select(Person.id, Person.name).where(Person.id.in_(ids)))).all()}
    rel_str = ", ".join(f"{role} = {names[oid]}" for role, oid in pairs
                        if role and names.get(oid))
    ctx = f"\n\nIDENTITÄT DES NUTZERS: Du sprichst mit {me.name} — das ist der Nutzer selbst."
    if rel_str:
        ctx += (f" Bekannte Beziehungen von {me.name}: {rel_str}. Wenn der Nutzer "
                "Verwandtschaftsbegriffe wie 'meine Frau', 'mein Mann', 'mein Sohn', "
                "'meine Tochter', 'meine Mutter', 'mein Vater' verwendet, löse sie ÜBER "
                "DIESE BEZIEHUNGEN zur konkreten Person auf und setze person=<Name>. "
                "Frage NICHT zurück, wer gemeint ist.")
    return ctx


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


def _filter_conditions(medientyp: Optional[str], jahr_von: Optional[int], jahr_bis: Optional[int],
                       person: Optional[str] = None, datum_von: Optional[str] = None,
                       datum_bis: Optional[str] = None, person2: Optional[str] = None,
                       ort: Optional[str] = None):
    """SQLAlchemy conditions for the structured filters the chat tools expose.
    (No is_trashed here — search_photos adds its own; _count adds it explicitly.)"""
    from datetime import datetime as _dt, timedelta as _td
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
    if datum_von:
        try: conds.append(Photo.taken_at >= _dt.fromisoformat(datum_von))
        except ValueError: pass
    if datum_bis:
        try: conds.append(Photo.taken_at < _dt.fromisoformat(datum_bis) + _td(days=1))
        except ValueError: pass
    # Restrict to photos that CONTAIN a named, recognised person (subquery, so no
    # join needed on the caller) — this is what makes "Lea traurig", "Lea an Ostern"
    # actually search within Lea's photos instead of for the word "Lea".
    def _person_cond(name: str):
        return Photo.id.in_(
            select(Face.photo_id).join(Person, Person.id == Face.person_id)
            .where(Person.name.ilike(f"%{name.strip()}%")))
    if person and person.strip():
        conds.append(_person_cond(person))
    # person2 = a SECOND named person who must ALSO be on the photo (co-occurrence) →
    # "ich mit meiner Tochter", "Lea und Anja zusammen". Each adds its own subquery, so
    # the photo must contain BOTH.
    if person2 and person2.strip():
        conds.append(_person_cond(person2))
    # ort = place filter across city / region / country (all ILIKE) so "in der Türkei",
    # "in Antalya", "in Köln" all work even though one photo may only have city OR country.
    if ort and ort.strip():
        o = f"%{ort.strip()}%"
        from sqlalchemy import or_ as _or
        conds.append(_or(Photo.city.ilike(o), Photo.country.ilike(o), Photo.location_name.ilike(o)))
    return conds


async def _retrieve(db: AsyncSession, query: str, settings: dict, limit: int = 20,
                    medientyp: Optional[str] = None, jahr_von: Optional[int] = None,
                    jahr_bis: Optional[int] = None, person: Optional[str] = None,
                    datum_von: Optional[str] = None, datum_bis: Optional[str] = None,
                    acl: Optional[list] = None, person2: Optional[str] = None,
                    ort: Optional[str] = None) -> List[dict]:
    # acl = photo_conditions(user): a restricted account only ever searches within the
    # photos it may see (else chat would surface the whole library).
    extra = _filter_conditions(medientyp, jahr_von, jahr_bis, person, datum_von,
                               datum_bis, person2, ort) + list(acl or [])
    # With strong structural filters (person/place/date) the semantic top-K is the wrong
    # tool — "alle Fotos von Lea in der Türkei" wants the WHOLE set, not 20 best matches.
    # So when filters are present and the free-text query is weak/empty, widen the net.
    if (person or person2 or ort or datum_von or jahr_von) and len((query or "").strip()) < 12:
        limit = max(limit, 60)
    photos = await search_photos(db, query or "", settings, limit=limit,
                                 extra_conditions=extra or None)
    return await _fused_records(db, photos)


async def _count(db: AsyncSession, medientyp: Optional[str], jahr_von: Optional[int],
                 jahr_bis: Optional[int], person: Optional[str], acl: Optional[list] = None) -> dict:
    """Exact count for 'wie viele …' questions — structural filters, not top-K search."""
    conds = _filter_conditions(medientyp, jahr_von, jahr_bis) + [Photo.is_trashed == False] + list(acl or [])  # noqa: E712
    q = select(func.count(func.distinct(Photo.id))).select_from(Photo)
    if person and person.strip():
        q = (q.join(Face, Face.photo_id == Photo.id)
              .join(Person, Person.id == Face.person_id)
              .where(Person.name.ilike(f"%{person.strip()}%")))
    q = q.where(*conds)
    n = await db.scalar(q)
    return {"anzahl": int(n or 0), "medientyp": medientyp or "beide",
            "jahr_von": jahr_von, "jahr_bis": jahr_bis, "person": person}


async def _temporal_bounds(db: AsyncSession, person: Optional[str], person2: Optional[str] = None,
                           medientyp: Optional[str] = None, jahr_von: Optional[int] = None,
                           jahr_bis: Optional[int] = None, acl: Optional[list] = None) -> dict:
    """Earliest & latest DATED photo of a person (optionally two people TOGETHER on
    one photo). Answers 'wann zum ersten/letzten Mal …' precisely — unlike semantic
    search this is sorted by DATE, so the true first/last is never missed."""
    conds = _filter_conditions(medientyp, jahr_von, jahr_bis) + [
        Photo.is_trashed == False, Photo.taken_at.isnot(None)] + list(acl or [])  # noqa: E712

    def _has(name: str):
        return Photo.id.in_(
            select(Face.photo_id).join(Person, Person.id == Face.person_id)
            .where(Person.name.ilike(f"%{name.strip()}%")))

    if person and person.strip():
        conds.append(_has(person))
    if person2 and person2.strip():
        conds.append(_has(person2))
    rows = (await db.execute(
        select(Photo.id, Photo.taken_at).where(*conds).order_by(Photo.taken_at.asc())
    )).all()
    if not rows:
        return {"treffer": 0}
    first, last = rows[0], rows[-1]
    return {"treffer": len(rows),
            "erstes_datum": str(first[1])[:10], "erstes_foto_id": first[0],
            "letztes_datum": str(last[1])[:10], "letztes_foto_id": last[0]}


async def _image_parts(db: AsyncSession, ids: List[int], max_n: int) -> list:
    """Gemini inline_data parts for the top-N hits' thumbnails (SSD, JPEG) so the
    multimodal model can SEE the photos — answers details no description captured.
    Each image is preceded by a '#id' text part so it can correlate them."""
    if not ids or max_n <= 0:
        return []
    ids = ids[:max_n]
    rows = (await db.execute(
        select(Photo.id, Photo.thumb_medium, Photo.thumb_small).where(Photo.id.in_(ids))
    )).all()
    path_by = {r[0]: (r[1] or r[2]) for r in rows}
    parts: list = []
    for pid in ids:
        path = path_by.get(pid)
        if not path or not os.path.exists(path):
            continue
        try:
            with open(path, "rb") as fh:
                b64 = base64.b64encode(fh.read()).decode()
            parts.append({"text": f"Foto #{pid}:"})
            parts.append({"inline_data": {"mime_type": "image/jpeg", "data": b64}})
        except Exception:
            pass
    return parts


async def _resolve_action_photo_ids(db: AsyncSession, settings: dict, args: dict, limit: int = 1000) -> list:
    """Photo ids matching a chat action's args (suchbegriff + person + medientyp/jahr)."""
    from app.models.photo import Photo
    from app.models.face import Face
    from app.models.person import Person
    conds = _filter_conditions(args.get("medientyp"), args.get("jahr_von"), args.get("jahr_bis"))
    conds.append(Photo.is_trashed == False)  # noqa: E712
    person = (args.get("person") or "").strip()
    if person:
        conds.append(Photo.id.in_(
            select(Face.photo_id).join(Person, Person.id == Face.person_id)
            .where(Person.name.ilike(f"%{person}%"))
        ))
    sb = (args.get("suchbegriff") or "").strip()
    if sb:
        photos = await search_photos(db, sb, settings, limit=limit, extra_conditions=conds or None)
        return [p.id for p in photos]
    rows = (await db.execute(
        select(Photo.id).where(*conds).order_by(Photo.taken_at.desc().nullslast()).limit(limit)
    )).all()
    return [r[0] for r in rows]


async def _action_create_album(db: AsyncSession, settings: dict, args: dict) -> dict:
    from app.models.album import Album, AlbumPhoto, AlbumType
    from app.models.person import Person
    name = (args.get("name") or "Album").strip()[:256]
    person = (args.get("person") or "").strip()
    sb = (args.get("suchbegriff") or "").strip()

    # Person-only request (e.g. "Album mit allen Fotos von Lea") → a SMART album:
    # auto-updating, holds ALL of that person's photos (no 1000 cap — that was the
    # "Lea Marie hat nur 1000 Bilder" bug).
    if person and not sb:
        pids = [r[0] for r in (await db.execute(
            select(Person.id).where(Person.name.ilike(f"%{person}%")))).all()]
        if pids:
            crit: dict = {"person_ids": pids, "person_match": "any"}
            mt = args.get("medientyp")
            if mt in ("bild", "video"):
                crit["media_type"] = "photo" if mt == "bild" else "video"
            album = Album(name=name, album_type=AlbumType.smart, smart_criteria=crit)
            db.add(album)
            await db.flush()
            from app.api.routes.albums import _populate_smart
            await _populate_smart(album, db)
            await db.commit()
            cnt = await db.scalar(select(func.count()).where(AlbumPhoto.album_id == album.id))
            return {"ok": True, "album_id": album.id, "name": name, "anzahl": int(cnt or 0), "smart": True}

    # Otherwise (free-text search etc.) → a manual album, but with a generous cap.
    ids = await _resolve_action_photo_ids(db, settings, args, limit=20000)
    if not ids:
        return {"ok": False, "info": "Keine passenden Fotos gefunden — kein Album erstellt."}
    album = Album(name=name, album_type=AlbumType.manual, cover_photo_id=ids[0])
    db.add(album)
    await db.flush()
    for i, pid in enumerate(ids):
        db.add(AlbumPhoto(album_id=album.id, photo_id=pid, sort_order=i))
    await db.commit()
    return {"ok": True, "album_id": album.id, "name": name, "anzahl": len(ids)}


async def _action_favorite(db: AsyncSession, settings: dict, args: dict) -> dict:
    from sqlalchemy import update as _upd
    from app.models.photo import Photo
    ids = await _resolve_action_photo_ids(db, settings, args)
    if not ids:
        return {"ok": False, "info": "Keine passenden Fotos gefunden."}
    await db.execute(_upd(Photo).where(Photo.id.in_(ids)).values(is_favorite=True))
    await db.commit()
    return {"ok": True, "anzahl": len(ids)}


async def _gemini_agent(message: str, history: list, settings: dict, db: AsyncSession, user=None) -> dict:
    # Chat may use its OWN Gemini key (Einstellungen → KI-Chat); falls back to the
    # shared image-AI key so existing setups keep working.
    key = (settings.get("chat.gemini.api_key") or settings.get("ai.gemini.api_key") or "").strip()
    if not key:
        return {"answer": "Kein Gemini-API-Key hinterlegt (Einstellungen → KI-Chat).", "photo_ids": []}
    model = settings.get("chat.gemini.model") or settings.get("ai.gemini.model", "gemini-2.5-flash")
    base = "https://generativelanguage.googleapis.com/v1beta"
    _filter_props = {
        "person": {"type": "string", "description": "Name einer ERKANNTEN Person — schränkt auf Fotos MIT dieser Person ein. Nutze das IMMER, wenn die Frage einen Namen enthält (z. B. 'Lea traurig' → person='Lea', suchbegriff='traurig weinen')."},
        "person2": {"type": "string", "description": "ZWEITE Person, die GEMEINSAM mit 'person' auf dem Foto sein muss. Für 'X mit Y', 'ich und meine Tochter', 'Lea und Anja zusammen'. Bei 'ich/mir/mich' setze hier deinen eigenen Namen aus der Identität."},
        "ort": {"type": "string", "description": "Ortsfilter (Stadt, Region ODER Land), z. B. ort='Türkei', ort='Antalya', ort='Köln'. Nutze das IMMER bei Ortsangaben ('in der Türkei', 'in Köln'). Für Länder den deutschen Landesnamen verwenden."},
        "medientyp": {"type": "string", "enum": ["bild", "video", "beide"],
                      "description": "Nur Bilder, nur Videos, oder beide. WICHTIG: fragt der Nutzer nach Videos → 'video', nach Bildern/Fotos → 'bild'."},
        "jahr_von": {"type": "integer", "description": "frühestes Jahr (inkl.), z. B. 2018"},
        "jahr_bis": {"type": "integer", "description": "spätestes Jahr (inkl.), z. B. 2020"},
        "datum_von": {"type": "string", "description": "Frühestes Datum (inkl.) als YYYY-MM-DD. Für konkrete Ereignisse/Feiertage rechne den Zeitraum SELBST aus, z. B. Ostern 2022 → datum_von='2022-04-15', datum_bis='2022-04-18'; Weihnachten 2021 → 2021-12-24..2021-12-26."},
        "datum_bis": {"type": "string", "description": "Spätestes Datum (inkl.) als YYYY-MM-DD."},
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
        {
            "name": "zeitliche_eckdaten",
            "description": "Liefert das FRÜHESTE und SPÄTESTE Foto-Datum für eine Person (optional zwei "
                           "Personen GEMEINSAM auf einem Foto). Nutze das für 'wann habe ich X das erste "
                           "Mal getroffen/gesehen', 'seit wann kenne ich X', 'wann zuletzt …' — die normale "
                           "Suche ist nach Relevanz sortiert und verpasst das wirklich früheste/späteste Foto.",
            "parameters": {"type": "object", "properties": {
                "person": {"type": "string", "description": "Name der Person (Pflicht), z. B. 'Anja'"},
                "person2": {"type": "string", "description": "Optional: zweite Person, die GEMEINSAM mit 'person' auf demselben Foto sein muss — z. B. der Nutzer selbst bei 'wann habe ICH X getroffen'."},
                "medientyp": _filter_props["medientyp"], "jahr_von": _filter_props["jahr_von"], "jahr_bis": _filter_props["jahr_bis"],
            }, "required": ["person"]},
        },
        {
            "name": "album_erstellen",
            "description": "Erstellt ein NEUES Album aus den passenden Fotos. Nutze das, wenn der Nutzer "
                           "ein Album anlegen/erstellen möchte (z. B. 'mach ein Album mit allen Strandfotos "
                           "von Lea 2022'). Kombiniert Suchbegriff, Person und Medientyp/Jahr-Filter.",
            "parameters": {"type": "object", "properties": {
                "name": {"type": "string", "description": "Name des neuen Albums"},
                "suchbegriff": {"type": "string", "description": "optional, wonach gefiltert wird"},
                "person": {"type": "string", "description": "optionaler Personenname"},
                **_filter_props,
            }, "required": ["name"]},
        },
        {
            "name": "als_favorit_markieren",
            "description": "Markiert die passenden Fotos als Favorit (Herz). Reversibel.",
            "parameters": {"type": "object", "properties": {
                "suchbegriff": {"type": "string"},
                "person": {"type": "string"},
                **_filter_props,
            }, "required": ["suchbegriff"]},
        },
    ]}
    contents = []
    for h in (history or [])[-8:]:
        role = "user" if h.get("role") == "user" else "model"
        contents.append({"role": role, "parts": [{"text": h.get("content", "")}]})
    contents.append({"role": "user", "parts": [{"text": message}]})

    seen_ids: list = []
    seen_recs: dict = {}   # id → fused record (description/date/place) for a rich gallery reply
    # Multimodal: send the top hits' thumbnails so Gemini can SEE them. Budget caps
    # total images across the conversation to bound token cost (chat.vision=off disables).
    vision = str(settings.get("chat.vision", "true")).lower() != "false"
    img_budget = 8
    # Identity block (who is the user + relations) so 'meine Frau' resolves without
    # a clarifying round-trip.
    from app.core.access import photo_conditions, _is_unrestricted
    acl = photo_conditions(user)                 # [] for admin/open; folder/date/person scope otherwise
    restricted = not _is_unrestricted(user)      # restricted accounts get read-only chat
    system_text = SYSTEM + await _identity_context(db, settings, user)
    async with httpx.AsyncClient(timeout=90) as client:
        for _ in range(5):  # allow a few tool round-trips
            payload = {
                "system_instruction": {"parts": [{"text": system_text}]},
                "contents": contents,
                "tools": [tool],
                # gemini-2.5-flash runs dynamic "thinking" by default — with a heavy
                # tool/system prompt it burned ~2 min even for a one-line reply.
                # Disable it: this is retrieval-grounded Q&A, not a reasoning task.
                "generationConfig": {"thinkingConfig": {"thinkingBudget": 0}},
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
                                            args.get("jahr_bis"), args.get("person"), acl=acl)
                        contents.append({"role": "user", "parts": [{"functionResponse": {
                            "name": c["name"], "response": resp}}]})
                    elif c.get("name") == "zeitliche_eckdaten":
                        resp = await _temporal_bounds(db, args.get("person"), args.get("person2"),
                                                      args.get("medientyp"), args.get("jahr_von"),
                                                      args.get("jahr_bis"), acl=acl)
                        eids = [resp[k] for k in ("erstes_foto_id", "letztes_foto_id") if resp.get(k)]
                        seen_ids.extend(eids)
                        if eids:
                            photos = (await db.execute(select(Photo).where(Photo.id.in_(eids)))).scalars().all()
                            for rrec in await _fused_records(db, photos):
                                seen_recs.setdefault(rrec["id"], rrec)
                        contents.append({"role": "user", "parts": [{"functionResponse": {
                            "name": c["name"], "response": resp}}]})
                    elif c.get("name") in ("album_erstellen", "als_favorit_markieren"):
                        # Write actions stay disabled for restricted accounts (read-only chat).
                        if restricted:
                            resp = {"fehler": "Aktionen sind in diesem Konto nicht verfügbar."}
                        elif c.get("name") == "album_erstellen":
                            resp = await _action_create_album(db, settings, args)
                        else:
                            resp = await _action_favorite(db, settings, args)
                        contents.append({"role": "user", "parts": [{"functionResponse": {
                            "name": c["name"], "response": resp}}]})
                    else:
                        recs = await _retrieve(db, args.get("suchbegriff", ""), settings,
                                               medientyp=args.get("medientyp"),
                                               jahr_von=args.get("jahr_von"), jahr_bis=args.get("jahr_bis"),
                                               person=args.get("person"), person2=args.get("person2"),
                                               ort=args.get("ort"),
                                               datum_von=args.get("datum_von"), datum_bis=args.get("datum_bis"),
                                               acl=acl)
                        seen_ids.extend([rrec["id"] for rrec in recs])
                        for rrec in recs:
                            seen_recs.setdefault(rrec["id"], rrec)
                        contents.append({"role": "user", "parts": [{"functionResponse": {
                            "name": c["name"], "response": {"treffer": recs}}}]})
                        if vision and img_budget > 0 and recs:
                            imgs = await _image_parts(db, [r["id"] for r in recs], min(6, img_budget))
                            if imgs:
                                contents.append({"role": "user", "parts":
                                    [{"text": "Die Bilder zu den Treffern (zur visuellen Beantwortung):"}] + imgs})
                                img_budget -= sum(1 for p in imgs if "inline_data" in p)
                continue
            text = " ".join(p["text"] for p in parts if "text" in p).strip()
            # Show the photos the answer ACTUALLY CITES (#id), not every photo the
            # agent skimmed while reasoning — otherwise a "wann/wo …" answer about one
            # photo would display loosely-related semantic hits years off. Only fall
            # back to the full seen set when the model cited nothing (e.g. "zeig mir …").
            import re as _re
            cited = list(dict.fromkeys(int(m) for m in _re.findall(r"#(\d+)", text)))
            if cited:
                missing = [i for i in cited if i not in seen_recs]
                if missing:
                    ph = (await db.execute(select(Photo).where(Photo.id.in_(missing)))).scalars().all()
                    for rrec in await _fused_records(db, ph):
                        seen_recs.setdefault(rrec["id"], rrec)
                uniq = [i for i in cited if i in seen_recs]
            else:
                uniq = list(dict.fromkeys(seen_ids))
            return {"answer": text or "(keine Antwort)", "photo_ids": uniq,
                    "photos": [seen_recs[i] for i in uniq if i in seen_recs]}
    _u = list(dict.fromkeys(seen_ids))
    return {"answer": "Abgebrochen (zu viele Tool-Schritte).", "photo_ids": _u,
            "photos": [seen_recs[i] for i in _u if i in seen_recs]}


async def _local_rag(message: str, settings: dict, db: AsyncSession, user=None) -> dict:
    from app.core.access import photo_conditions
    recs = await _retrieve(db, message, settings, acl=photo_conditions(user))
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
    return {"answer": answer, "photo_ids": [r["id"] for r in recs], "photos": recs}


async def chat(message: str, history: list, settings: dict, db: AsyncSession,
               provider: Optional[str] = None, user=None) -> dict:
    prov = (provider or settings.get("chat.provider") or "gemini").lower()
    if prov == "local":
        return await _local_rag(message, settings, db, user=user)
    return await _gemini_agent(message, history, settings, db, user=user)
