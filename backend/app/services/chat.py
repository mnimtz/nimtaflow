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

from app.models.photo import Photo, PhotoStatus
from app.models.face import Face
from app.models.person import Person


def _strict_name(name):
    """Strikter Person-Namen-Match: exakt oder Vorname-Prefix.
    Vorher überall `ilike("%name%")` — hat "Lea" als Match für "Leandra" akzeptiert.
    photo_search.py nutzt schon die strikte Regel; jetzt konsistent.
    """
    from sqlalchemy import or_ as _or, func as _func
    from app.models.person import Person
    n = (name or "").strip().lower()
    if not n:
        return Person.name.is_(None)  # nichts trifft → leerer Filter
    return _or(_func.lower(Person.name) == n,
               _func.lower(Person.name).like(f"{n} %"))

from app.models.tag import Tag, PhotoTag
from app.services.photo_search import search_photos

SYSTEM = (
    "Du bist der Foto-Assistent von NimtaFlow und beantwortest Fragen zur privaten "
    "Foto-/Videosammlung des Nutzers auf Deutsch. Du hast VIELE Werkzeuge — nutze "
    "sie großzügig: lieber 2-3 Werkzeuge nacheinander aufrufen und eine echte Antwort "
    "geben als sofort 'ich habe nichts gefunden'. Wenn ein Werkzeug 0 Treffer hat, "
    "PROBIER ein anderes, lockere Filter, formuliere den suchbegriff neu, oder frage "
    "kurz nach. Zu jedem Foto bekommst du reichhaltigen Kontext: Datum + Wochentag + "
    "Tageszeit, Ort (Stadt, Region, Land, ortsname), erkannte PERSONEN, Tags, Alben-"
    "Zugehörigkeit, volle Beschreibung, Nutzer-Notiz, Titel, Favorit/Bewertung, Kamera, "
    "und (bei Videos) Dauer. Kombiniere all das: eine anonym beschriebene Person ist "
    "sehr wahrscheinlich eine der erkannten benannten Personen (z. B. „Person im blauen "
    "Hemd“ + erkannt „Günter Nimtz“ → die Person im blauen Hemd ist Günter Nimtz). "
    "Ein Foto vom Sonntagabend mit Tag „Grillen“ und Personen „Marcus, Anja“ ist eine "
    "Familienrunde. Antworte hauptsächlich anhand der gefundenen Fotos, DARFST aber auch "
    "vernünftige Schlussfolgerungen ziehen wenn Datum/Ort/Personen/Tags eindeutig sind — "
    "sag dann klar 'wahrscheinlich' oder 'vermutlich'. Bei wirklich 0 Treffern ehrlich "
    "sagen und Alternativen vorschlagen (andere Interpretation, anderer Zeitraum). "
    "Nenne relevante Fotos per #id. "
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
    "Auch bei KURZEN, KOMMAGETRENNTEN Anfragen wie 'Boston, Frank' oder 'Frank Boston' "
    "(ohne 'in', ohne 'mit'), erkenne Person und Ort aktiv: eines der Wörter ist meist ein "
    "Name (person), das andere ein Ort (ort). Setze BEIDE Parameter — niemals einfach als "
    "Freitext-suchbegriff durchreichen, sonst mischen sich Ergebnisse. "
    "Zu DATUM/EREIGNISSEN: Für konkrete Anlässe rechne den Zeitraum selbst aus und "
    "nutze datum_von/datum_bis (YYYY-MM-DD), z. B. 'Lea an Ostern 2022' → person='Lea', "
    "datum_von='2022-04-15', datum_bis='2022-04-18'. "
    "Zu 'WANN lernte X …' / 'wann konnte X das erste Mal …' / 'ab wann …' (Meilensteine "
    "wie laufen, sprechen, schwimmen, Fahrrad fahren): nutze IMMER zeitliche_eckdaten "
    "mit person=X UND suchbegriff='<Meilenstein> <Synonyme>'. Beispiele: "
    "'wann lernte Lea laufen' → zeitliche_eckdaten(person='Lea', suchbegriff='laufen erste Schritte krabbeln stehen'); "
    "'wann konnte Lea schwimmen' → zeitliche_eckdaten(person='Lea', suchbegriff='schwimmen wasser schwimmbad'); "
    "'ab wann fuhr Lea Fahrrad' → zeitliche_eckdaten(person='Lea', suchbegriff='fahrrad rad bicycle'). "
    "Antworte mit dem 'erstes_datum' und dem passenden Foto #id — das ist die verlässlich "
    "früheste Antwort (datumssortiert, nicht relevanzsortiert). "
    "Für allgemeine 'WANN …'-Fragen ohne Meilenstein: normale suche_fotos, schau die DATEN "
    "der Treffer an, nenne das früheste passende Datum. "
    "Für 'wann habe ich X das erste Mal getroffen/gesehen', 'seit wann kenne ich X', "
    "'wann zuletzt …' nutze IMMER das Werkzeug zeitliche_eckdaten (person=X) — es liefert "
    "das wirklich früheste/späteste Foto-Datum (datumssortiert). Geht es um GEMEINSAME "
    "Fotos mit dir, setze zusätzlich person2=<dein eigener Name aus der Identität>. "
    "Nenne dann erstes_datum bzw. letztes_datum als Antwort und das zugehörige Foto per #id. "
    "Zu ALTER/GEBURTSTAG ('X. Geburtstag', 'wann wurde X 40', 'wie alt war X im Jahr Y', "
    "'X als sie 5 war'): nutze IMMER das Werkzeug geburtstag_datum(person, alter) — es liest "
    "das HINTERLEGTE Geburtsdatum und rechnet das exakte Datum aus (rate NIE selbst ein "
    "Geburtsdatum/Alter aus Fotos). Hat die Person kein Geburtsdatum hinterlegt, sag das ehrlich "
    "und schlage vor, es unter Personen einzutragen. Sonst suche danach mit person=X und den "
    "gelieferten datum_von/datum_bis, um die Geburtstags-Fotos zu finden. "
    "Du kannst auch HANDELN: Möchte der Nutzer ein Album anlegen, nutze "
    "album_erstellen; sollen Fotos favorisiert werden, nutze als_favorit_markieren. "
    "Bestätige danach kurz, was du getan hast (Albumname + Anzahl). "
    "Für ein VIDEO/Highlight ('mach ein Video von …', 'erstell ein Highlight', 'wie hat sich X "
    "verändert' als Video) nutze highlight_erstellen mit passendem thema. Bei einem Video zu "
    "einem ORT/einer Reise erst album_erstellen (mit ort/jahr), dann highlight_erstellen "
    "thema='trip' mit dem gelieferten album_id. Sag danach, dass das Rendern ein paar Minuten dauert. "
    "NEUE analytische WERKZEUGE — nutze sie wenn die Frage sie natürlich passt: "
    "'mit wem ist X am häufigsten' → personen_zusammenhang(person=X). "
    "'wo war X am meisten', 'welche Länder mit X' → orte_von_person(person=X). "
    "'wann sehe ich X meistens', 'sind wir eher Wochenende unterwegs' → alltag_muster(person=X). "
    "'was war noch bei diesem Foto', 'zeig mehr aus dem Tag/Ausflug' → kontext_um_foto(photo_id=…). "
    "'zeig ähnliche', 'weitere Fotos wie dieses' → aehnliche_szenen(photo_id=…). "
    "Kombiniere Werkzeuge — z. B. erst suche_fotos → dann kontext_um_foto vom besten Treffer, "
    "oder erst zeitliche_eckdaten → dann kontext_um_foto vom erstes_foto_id für die Erzählung. "
    "Zu STATUS/VERARBEITUNG: Für Fragen zur eigenen Bibliothek (wie viele Fotos/Videos, "
    "wie viele noch in Verarbeitung, wie viele ohne Beschreibung, ältestes/neuestes Foto) "
    "nutze bibliothek_status. Für Fragen zum SERVER-BETRIEB (Queue-Auslastung, laufen die "
    "Worker, wie lange dauert die Verarbeitung noch, Leitstand) nutze leitstand_status — das "
    "ist nur für Administratoren; kommt kein_zugriff=true zurück, sag höflich, dass diese "
    "Betriebsdaten dem Administrator vorbehalten sind. Restzeit-Angaben sind immer nur grobe "
    "Schätzungen — kennzeichne sie als solche. "
    "Zu ZUSAMMENFASSUNGEN/RÜCKBLICKEN ('erzähl mir von unserem Urlaub in X', 'Rückblick 2023', "
    "'fass den Sommer zusammen', 'wo war ich überall', 'wen sehe ich am häufigsten') nutze das "
    "Werkzeug rueckblick (Aggregat: Anzahl, Zeitspanne, Top-Orte, Top-Personen) und schreibe daraus "
    "eine kurze, warme ERZÄHLUNG mit konkreten Orten/Personen/Zeiträumen — kein trockenes Aufzählen. "
    "Zu NAVIGATION: Will der Nutzer zu einer ANSICHT/Seite (nicht nur Fotos sehen), nutze "
    "oeffne_ansicht — z. B. 'geh zu den Personen'/'zeig alle Reisen' (Übersicht) oder 'öffne "
    "Anjas Seite'/'zeig unsere Kroatien-Reise' (mit name). Für reines Anzeigen von Fotos "
    "hingegen suche_fotos. Nach dem Navigieren kurz bestätigen, wohin. "
    "ANZEIGEN & KNAPP BLEIBEN: Bei reinen Anzeige-/Suchwünschen ('zeig mir …', 'Fotos von …') "
    "antworte in 1–2 kurzen Sätzen und VERLASS dich auf die Galerie — der Nutzer sieht ALLE Treffer "
    "dort, du musst sie NICHT einzeln als Text aufzählen (keine Fotobeschreibungs-Listen/Textwände). "
    "Das Werkzeug suche_fotos liefert 'gesamt_anzahl' (die WAHRE Trefferzahl der ganzen Galerie, nicht "
    "nur die zurückgegebenen Beispiele) — nenne diese Zahl ('Ich habe 240 Fotos von Anja gefunden – "
    "sie sind in deiner Galerie'), NICHT die Länge der 'treffer'-Beispielliste. Höchstens 1–2 Fotos per "
    "#id hervorheben, wenn es die Antwort wirklich stützt. "
    "PROAKTIV: Wenn es sinnvoll ist, biete am ENDE deiner Antwort 2–3 kurze Folge-Vorschläge "
    "an — als allerletzte Zeile im Format 'VORSCHLÄGE: <a> | <b> | <c>'. Sie müssen KNAPP sein "
    "(Tap-Buttons, max. ~4 Wörter), konkret und auf den Kontext bezogen, z. B. bei Fototreffern "
    "'Als Album speichern | Auch <Nachbarjahr> zeigen | Nur Videos'; bei einer Person 'Zeitraum "
    "anzeigen | Gemeinsame Fotos'. Formuliere sie als Anweisung, die man direkt wieder an dich "
    "stellen könnte. Lass die Zeile WEG, wenn keine sinnvollen Vorschläge existieren."
)


def _today_block() -> str:
    """Heutiges Datum + vorberechnete Zeitfenster für RELATIVE Angaben, damit der Agent
    'letzte Woche', 'gestern', 'diesen Monat' zuverlässig in datum_von/datum_bis übersetzt
    statt über alle Jahre zu suchen. Wir rechnen die Wochen-/Monatsgrenzen HIER (Python),
    damit das Modell nicht selbst rechnen muss. Nutzt Europe/Berlin — damit stimmt
    'heute'/'gestern' auch kurz nach Mitternacht."""
    from datetime import timedelta as _td
    from datetime import datetime as _dtt
    from zoneinfo import ZoneInfo
    t = _dtt.now(ZoneInfo("Europe/Berlin")).date()
    y = t - _td(days=1)                                  # gestern
    this_mon = t - _td(days=t.weekday())                 # Montag DIESER Woche
    last_mon = this_mon - _td(days=7)                    # Montag LETZTE Woche
    last_sun = this_mon - _td(days=1)                    # Sonntag LETZTE Woche
    m_start = t.replace(day=1)                           # 1. dieses Monats
    lm_end = m_start - _td(days=1)                        # letzter Tag Vormonat
    lm_start = lm_end.replace(day=1)                     # 1. Vormonat
    d7 = t - _td(days=7)                                 # letzte 7 Tage
    d30 = t - _td(days=30)                               # letzte 30 Tage
    iso = lambda x: x.isoformat()
    return (
        f"\n\nHEUTIGES DATUM: {iso(t)}. Bei RELATIVEN Zeitangaben MUSST du datum_von/datum_bis "
        f"(YYYY-MM-DD) setzen — sonst wird fälschlich über alle Jahre gesucht. Nutze exakt diese "
        f"vorgerechneten Fenster:\n"
        f"• 'heute' → datum_von={iso(t)}, datum_bis={iso(t)}\n"
        f"• 'gestern' → datum_von={iso(y)}, datum_bis={iso(y)}\n"
        f"• 'letzte Woche'/'vorige Woche' → datum_von={iso(last_mon)}, datum_bis={iso(last_sun)}\n"
        f"• 'diese Woche' → datum_von={iso(this_mon)}, datum_bis={iso(t)}\n"
        f"• 'letzten 7 Tage'/'die Tage'/'kürzlich' → datum_von={iso(d7)}, datum_bis={iso(t)}\n"
        f"• 'letzten 30 Tage'/'letzten Monat' (rollierend) → datum_von={iso(d30)}, datum_bis={iso(t)}\n"
        f"• 'diesen Monat' → datum_von={iso(m_start)}, datum_bis={iso(t)}\n"
        f"• 'letzten Monat'/'im Vormonat' (Kalendermonat) → datum_von={iso(lm_start)}, datum_bis={iso(lm_end)}\n"
        f"• 'dieses Jahr' → jahr_von={t.year}, jahr_bis={t.year}; 'letztes Jahr' → jahr_von={t.year-1}, jahr_bis={t.year-1}.\n"
        f"Für 'vor N Tagen/Wochen/Monaten' rechne analog von heute aus. Kombiniere das IMMER mit "
        f"person, wenn ein Name genannt ist (z. B. 'Anja letzte Woche' → person='Anja', "
        f"datum_von={iso(last_mon)}, datum_bis={iso(last_sun)})."
    )


async def _identity_context(db: AsyncSession, settings: dict, user=None) -> str:
    """Tell the assistant WHO the user is and their relations, so 'meine Frau' /
    'mein Sohn' resolve instantly instead of 'wer ist deine Frau?'. Prefers the
    LOGGED-IN user's linked person (access_config.person_id or User.person_id) so
    multi-user installs answer per-user; falls back to the global
    relationships.self_person_id."""
    sid = None
    if user is not None:
        # Eingeloggter Nutzer → IMMER die EIGENE Verknüpfung (access_config.person_id
        # bzw. user.person_id), aus dem Login abgeleitet. KEIN Rückfall auf den globalen
        # self_person_id — sonst hielte der Chat einen nicht-verknüpften Nutzer
        # fälschlich für den Besitzer/Admin (Multi-User-Identitätsleck).
        cfg = getattr(user, "access_config", None) or {}
        sid = cfg.get("person_id") or getattr(user, "person_id", None)
    else:
        # Kein Login (offener / Single-User-Modus) → globaler Besitzer.
        sid = settings.get("relationships.self_person_id")
    try:
        sid = int(sid) if sid is not None else None
    except (TypeError, ValueError):
        sid = None
    if sid is None:
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
    """v1.539: Reicheres Record pro Foto — der Agent soll mit ALLEN Signalen
    argumentieren können. Datum + Wochentag + Uhrzeit + Ort (Stadt/Region/Land)
    + Personen + Tags (uncapped bis 40) + volle Beschreibung + Nutzer-Notiz
    + Titel + Album-Mitgliedschaft + Kamera + Favorit/Rating + Videodauer.
    Statt Info zu blockieren geben wir alles, was der Nutzer hat."""
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
    tags: dict = {}
    for pid, tname in (await db.execute(
        select(PhotoTag.photo_id, Tag.name).join(Tag, Tag.id == PhotoTag.tag_id)
        .where(PhotoTag.photo_id.in_(ids))
    )).all():
        tags.setdefault(pid, []).append(tname)
    # Album-Mitgliedschaft — verrät zusätzlichen menschlichen Kontext
    # ("in Album 'Kroatien 2023'"), den keine Beschreibung liefert.
    albums: dict = {}
    try:
        from app.models.album import AlbumPhoto, Album  # type: ignore
        for pid, aname in (await db.execute(
            select(AlbumPhoto.photo_id, Album.name).join(Album, Album.id == AlbumPhoto.album_id)
            .where(AlbumPhoto.photo_id.in_(ids), Album.name.isnot(None))
        )).all():
            if aname:
                albums.setdefault(pid, []).append(aname)
    except Exception:
        pass
    # Wochentag-Map (deutsch, kurz)
    _WD = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
    out = []
    for p in photos:
        desc = (p.description or "").strip()
        note = (getattr(p, "user_description", None) or "").strip()
        # Datum + Wochentag + Uhrzeit-Bucket → dem Agent das temporale
        # Muster verfügbar machen (Wochenende? Abend? Sommerferien?).
        datum = None; wtag = None; ustd = None
        if p.taken_at:
            try:
                datum = str(p.taken_at)[:10]
                wtag = _WD[p.taken_at.weekday()]
                h = p.taken_at.hour
                if h < 6:   ustd = "Nacht"
                elif h < 11: ustd = "Vormittag"
                elif h < 14: ustd = "Mittag"
                elif h < 18: ustd = "Nachmittag"
                elif h < 22: ustd = "Abend"
                else:       ustd = "Nacht"
            except Exception:
                pass
        # Ort so detailliert wie vorhanden (Stadt/Region/Land + location_name)
        ort_parts = [x for x in (p.city, getattr(p, "region", None), p.country) if x]
        loc_name = (getattr(p, "location_name", None) or "").strip()
        ort = ", ".join(ort_parts) or None
        rec = {
            "id": p.id,
            "datum": datum,
            "wochentag": wtag,
            "tageszeit": ustd,
            "ort": ort,
            "ortsname": loc_name or None,
            "titel": (getattr(p, "title", None) or "").strip() or None,
            "personen": sorted(people.get(p.id, [])) or None,
            "tags": (tags.get(p.id) or [])[:40] or None,
            "alben": (albums.get(p.id) or []) or None,
            "beschreibung": desc[:1500] or None,
            "notiz": note[:500] or None,
            "ist_video": bool(p.is_video),
            "favorit": bool(getattr(p, "is_favorite", False)),
            "bewertung": getattr(p, "rating", None) or None,
        }
        # Kamera-Kontext hilft für „Fotos von meiner alten Kamera" / „Handy-Fotos"
        cam = (getattr(p, "camera_make", None) or getattr(p, "camera_model", None))
        if cam: rec["kamera"] = str(cam)[:60]
        # Videodauer nur bei Video
        if p.is_video:
            dur = getattr(p, "video_duration", None) or getattr(p, "duration", None)
            if dur:
                try: rec["dauer_sek"] = int(float(dur))
                except Exception: pass
        out.append(rec)
    return out


def _filter_conditions(medientyp: Optional[str], jahr_von: Optional[int], jahr_bis: Optional[int],
                       person: Optional[str] = None, datum_von: Optional[str] = None,
                       datum_bis: Optional[str] = None, person2: Optional[str] = None,
                       ort: Optional[str] = None, person3: Optional[str] = None,
                       person4: Optional[str] = None):
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
    # STRIKT: exakt oder Prefix — vorher hat ilike("%name%") auch "Leandra" bei
    # "Lea" oder "Alexander" bei "Alex" getroffen. photo_search.py nutzt schon
    # dieselbe Regel; jetzt konsistent überall.
    def _person_cond(name: str):
        from sqlalchemy import or_ as _or_p, func as _func
        n = name.strip().lower()
        return Photo.id.in_(
            select(Face.photo_id).join(Person, Person.id == Face.person_id)
            .where(_or_p(_func.lower(Person.name) == n,
                          _func.lower(Person.name).like(f"{n} %"))))
    if person and person.strip():
        conds.append(_person_cond(person))
    # person2 = a SECOND named person who must ALSO be on the photo (co-occurrence) →
    # "ich mit meiner Tochter", "Lea und Anja zusammen". Each adds its own subquery, so
    # the photo must contain BOTH.
    if person2 and person2.strip():
        conds.append(_person_cond(person2))
    if person3 and person3.strip():
        conds.append(_person_cond(person3))
    if person4 and person4.strip():
        conds.append(_person_cond(person4))
    # ort = place filter across city / region / country / description. Präfixe wie
    # "Großraum", "Umgebung", "Nähe", "bei" verwerfen — sonst matcht
    # ILIKE '%Großraum Boston%' garantiert nichts. Bei erkannter Metro-Präfix zusätzlich
    # eine gelockerte Description-Suche.
    if ort and ort.strip():
        o_raw = ort.strip()
        import re as _re
        # Präfixe entfernen: "Großraum Boston" → "Boston", "in der Nähe von Köln" → "Köln"
        _m = _re.match(r"^(?:großraum|greater|umgebung|nähe|naehe|nahe|bei|in der nähe von|in der naehe von)\s+(?:von\s+)?(.+)$",
                       o_raw, _re.IGNORECASE)
        if _m:
            o_raw = _m.group(1).strip()
        # Prä-/Suffix "und Umgebung" ebenfalls stutzen.
        o_raw = _re.sub(r"\s+und\s+umgebung\s*$", "", o_raw, flags=_re.IGNORECASE).strip()
        o = f"%{o_raw}%"
        from sqlalchemy import or_ as _or
        conds.append(_or(Photo.city.ilike(o), Photo.country.ilike(o),
                         Photo.location_name.ilike(o), Photo.description.ilike(o)))
    return conds


async def _retrieve(db: AsyncSession, query: str, settings: dict, limit: int = 20,
                    medientyp: Optional[str] = None, jahr_von: Optional[int] = None,
                    jahr_bis: Optional[int] = None, person: Optional[str] = None,
                    datum_von: Optional[str] = None, datum_bis: Optional[str] = None,
                    acl: Optional[list] = None, person2: Optional[str] = None,
                    ort: Optional[str] = None, person3: Optional[str] = None,
                    person4: Optional[str] = None) -> List[dict]:
    extra = _filter_conditions(medientyp, jahr_von, jahr_bis, person, datum_von,
                               datum_bis, person2, ort, person3, person4) + list(acl or [])
    if (person or person2 or person3 or person4 or ort or datum_von or jahr_von) and len((query or "").strip()) < 12:
        limit = max(limit, 60)
    photos = await search_photos(db, query or "", settings, limit=limit,
                                 extra_conditions=extra or None)
    # Fallback-Retry: wenn strukturelle Filter (Ort/Datum) 0 Treffer produzieren,
    # locker eskalieren — erst Ort weglassen, dann Freitext-Search-Distanz erhöhen.
    # Bug-Beispiel: „Frank in Boston" 3 Fotos, „Großraum Boston" 0 — der User erwartet
    # min. das Personen-Match, nicht ein leeres Ergebnis.
    if not photos and (ort or datum_von):
        # 1. Retry ohne Ort
        if ort:
            extra_no_ort = _filter_conditions(medientyp, jahr_von, jahr_bis, person,
                                              datum_von, datum_bis, person2, None,
                                              person3, person4) + list(acl or [])
            photos = await search_photos(db, query or "", settings, limit=limit,
                                         extra_conditions=extra_no_ort or None)
    if not photos and (query or "").strip():
        # 2. Retry mit lockerem max_distance
        loose_settings = dict(settings)
        loose_settings["search.max_distance"] = "0.62"
        loose_settings["search.min_score"] = "0.15"
        photos = await search_photos(db, query or "", loose_settings, limit=limit,
                                     extra_conditions=extra or None)
    # v1.539: Wenn Person/Ort/Datum-Filter aktiv aber IMMER noch 0 Treffer
    # (auch nach loose retry) → volle strukturelle Suche ohne Freitext.
    # Der Nutzer erwartet bei „Frank in Boston" eher Frank UND Boston als leer.
    if not photos and extra:
        photos = await search_photos(db, "", settings, limit=limit,
                                     extra_conditions=extra)
    return await _fused_records(db, photos)


async def _structural_ids(db: AsyncSession, medientyp, jahr_von, jahr_bis, person,
                          person2, ort, datum_von, datum_bis, acl, cap: int = 20000,
                          person3: Optional[str] = None, person4: Optional[str] = None) -> List[int]:
    """ALLE passenden Foto-IDs — Cap 20000 (vorher 2000, war der „nur 2000 Bilder"-Bug
    im Chat-Galerie-Handoff). Rein strukturell (Person/Ort/Datum/Jahr/Medientyp)."""
    from app.models.photo import PhotoStatus
    conds = _filter_conditions(medientyp, jahr_von, jahr_bis, person, datum_von,
                               datum_bis, person2, ort, person3, person4) + list(acl or [])
    rows = await db.execute(
        select(Photo.id).where(Photo.status == PhotoStatus.done, Photo.is_trashed == False,  # noqa: E712
                               Photo.thumb_small.isnot(None), *conds)
        .order_by(Photo.taken_at.desc().nullslast()).limit(cap))
    return list(rows.scalars().all())


async def _count(db: AsyncSession, medientyp: Optional[str], jahr_von: Optional[int],
                 jahr_bis: Optional[int], person: Optional[str], acl: Optional[list] = None,
                 person2: Optional[str] = None, ort: Optional[str] = None,
                 datum_von: Optional[str] = None, datum_bis: Optional[str] = None,
                 person3: Optional[str] = None, person4: Optional[str] = None) -> dict:
    """Exact count for 'wie viele …' questions."""
    conds = _filter_conditions(medientyp, jahr_von, jahr_bis, person, datum_von,
                               datum_bis, person2, ort, person3, person4) + [Photo.is_trashed == False] + list(acl or [])  # noqa: E712
    n = await db.scalar(select(func.count(func.distinct(Photo.id))).select_from(Photo).where(*conds))
    return {"anzahl": int(n or 0), "medientyp": medientyp or "beide",
            "jahr_von": jahr_von, "jahr_bis": jahr_bis, "person": person,
            "person2": person2, "ort": ort}


async def _temporal_bounds(db: AsyncSession, person: Optional[str], person2: Optional[str] = None,
                           medientyp: Optional[str] = None, jahr_von: Optional[int] = None,
                           jahr_bis: Optional[int] = None, acl: Optional[list] = None,
                           suchbegriff: Optional[str] = None) -> dict:
    """Earliest & latest DATED photo of a person (optionally two people TOGETHER on
    one photo). Answers 'wann zum ersten/letzten Mal …' precisely — unlike semantic
    search this is sorted by DATE, so the true first/last is never missed.

    v1.538: optional `suchbegriff` filtert VOR dem MIN/MAX auf Fotos mit passender
    Beschreibung (ILIKE ODER-verkettet über die Wörter). Damit beantwortet der
    Chat „Wann lernte Lea laufen" korrekt: Personen-Filter + ILIKE 'lauf'/'schritt'/
    'krabbel'/'steh', MIN(taken_at) → früheste passende Szene."""
    conds = _filter_conditions(medientyp, jahr_von, jahr_bis) + [
        Photo.is_trashed == False, Photo.taken_at.isnot(None)] + list(acl or [])  # noqa: E712

    def _has(name: str):
        return Photo.id.in_(
            select(Face.photo_id).join(Person, Person.id == Face.person_id)
            .where(_strict_name(name)))

    if person and person.strip():
        conds.append(_has(person))
    if person2 and person2.strip():
        conds.append(_has(person2))
    if suchbegriff and suchbegriff.strip():
        import re as _re
        # Wortstämme mit ILIKE ODER-verkettet. Kurze/leere Wörter raus.
        toks = [t for t in _re.split(r"[\s,;/]+", suchbegriff.strip()) if len(t) >= 3]
        if toks:
            ors = []
            for t in toks:
                pat = f"%{t}%"
                ors.extend([Photo.description.ilike(pat),
                            Photo.location_name.ilike(pat)])
            from sqlalchemy import or_ as _or
            conds.append(_or(*ors))
    # v1.541 BIRTHDATE-SANITY: kein Foto von VOR der Geburt der Person liefern.
    # Sonst behauptet der Chat auf einem 2001er-Foto, Lea (geb. 2017) sei da drauf.
    if person and person.strip():
        bd = await db.scalar(select(Person.birthdate).where(_strict_name(person)).limit(1))
        if bd:
            conds.append(Photo.taken_at >= bd)
    # Aggregat statt LADEN ALLE ZEILEN: bei Personen mit 7000+ Fotos zog die alte
    # Query 7k Rows in Python-Liste (Timeout-Killer bei "wann lernte Lea laufen").
    # Wir brauchen nur MIN/MAX + je 1 Foto-ID an den Extremen.
    from sqlalchemy import func as _f
    agg = (await db.execute(
        select(_f.count().label("cnt"),
               _f.min(Photo.taken_at).label("mind"),
               _f.max(Photo.taken_at).label("maxd")).where(*conds))).one()
    if not agg.cnt:
        return {"treffer": 0}
    first_id = await db.scalar(
        select(Photo.id).where(*conds, Photo.taken_at == agg.mind).limit(1))
    last_id = await db.scalar(
        select(Photo.id).where(*conds, Photo.taken_at == agg.maxd).limit(1))
    return {"treffer": int(agg.cnt),
            "erstes_datum": str(agg.mind)[:10], "erstes_foto_id": first_id,
            "letztes_datum": str(agg.maxd)[:10], "letztes_foto_id": last_id}


async def _personen_zusammenhang(db: AsyncSession, person: str, top: int = 8,
                                 acl: Optional[list] = None) -> dict:
    """Wer war am häufigsten mit dieser Person zusammen auf Fotos? Aggregate über
    Face-Co-Occurrence pro Photo. Für 'mit wem ist Lea am häufigsten', 'wer sind
    Anjas engste Kontakte'."""
    if not person or not person.strip():
        return {"treffer": 0, "hinweis": "Kein Name angegeben."}
    from sqlalchemy import func as _f
    ref_ids = (await db.execute(select(Person.id).where(_strict_name(person)))).scalars().all()
    if not ref_ids:
        return {"treffer": 0, "hinweis": f"'{person}' ist nicht als Person hinterlegt."}
    photo_ids_sub = select(Face.photo_id).where(Face.person_id.in_(ref_ids))
    q = (select(Person.name, _f.count(_f.distinct(Face.photo_id)).label("n"))
         .join(Face, Face.person_id == Person.id)
         .where(Face.photo_id.in_(photo_ids_sub), Person.name.isnot(None),
                ~Person.id.in_(ref_ids), Person.name != "")
         .group_by(Person.name).order_by(_f.count(_f.distinct(Face.photo_id)).desc())
         .limit(int(top)))
    rows = (await db.execute(q)).all()
    return {"person": person,
            "gemeinsam_mit": [{"name": n, "gemeinsame_fotos": int(c)} for n, c in rows],
            "treffer": len(rows)}


async def _orte_von_person(db: AsyncSession, person: str, top: int = 12,
                           acl: Optional[list] = None) -> dict:
    """Wo war eine Person am häufigsten? Aggregate über (city, country) mit counts.
    Für 'wo war Lea am meisten', 'welche Länder haben wir besucht'."""
    if not person or not person.strip():
        return {"treffer": 0}
    from sqlalchemy import func as _f
    ref_ids = (await db.execute(select(Person.id).where(_strict_name(person)))).scalars().all()
    if not ref_ids:
        return {"treffer": 0}
    photo_sub = select(Face.photo_id).where(Face.person_id.in_(ref_ids))
    cond = [Photo.id.in_(photo_sub), Photo.is_trashed == False,   # noqa: E712
            Photo.city.isnot(None)] + list(acl or [])
    q = (select(Photo.city, Photo.country, _f.count().label("n"),
                _f.min(Photo.taken_at).label("erstmalig"),
                _f.max(Photo.taken_at).label("letztmalig"))
         .where(*cond).group_by(Photo.city, Photo.country)
         .order_by(_f.count().desc()).limit(int(top)))
    rows = (await db.execute(q)).all()
    return {"person": person, "orte": [
        {"stadt": c, "land": co, "fotos": int(n),
         "von": str(mn)[:10] if mn else None, "bis": str(mx)[:10] if mx else None}
        for c, co, n, mn, mx in rows]}


async def _alltag_muster(db: AsyncSession, person: str,
                         acl: Optional[list] = None) -> dict:
    """Wochentag- und Uhrzeit-Muster der Fotos einer Person. Für 'wann sehe ich
    Lea meistens', 'sind Reise-Fotos eher Wochenende'."""
    if not person or not person.strip():
        return {"treffer": 0}
    from sqlalchemy import func as _f
    ref_ids = (await db.execute(select(Person.id).where(_strict_name(person)))).scalars().all()
    if not ref_ids:
        return {"treffer": 0}
    photo_sub = select(Face.photo_id).where(Face.person_id.in_(ref_ids))
    cond = [Photo.id.in_(photo_sub), Photo.is_trashed == False,   # noqa: E712
            Photo.taken_at.isnot(None)] + list(acl or [])
    # dow: 0=Sonntag in Postgres → wir mappen: extract('isodow') = 1..7 Mo..So
    q = (select(_f.extract("isodow", Photo.taken_at).label("dow"),
                _f.extract("hour", Photo.taken_at).label("h"),
                _f.count().label("n"))
         .where(*cond).group_by("dow", "h"))
    rows = (await db.execute(q)).all()
    _WD = {1: "Mo", 2: "Di", 3: "Mi", 4: "Do", 5: "Fr", 6: "Sa", 7: "So"}
    by_wd = {v: 0 for v in _WD.values()}
    by_tz = {"Nacht": 0, "Vormittag": 0, "Mittag": 0, "Nachmittag": 0, "Abend": 0}
    for dow, h, n in rows:
        if dow: by_wd[_WD.get(int(dow), "?")] = by_wd.get(_WD.get(int(dow), "?"), 0) + int(n)
        hi = int(h or 0)
        bucket = ("Nacht" if hi < 6 else "Vormittag" if hi < 11 else "Mittag" if hi < 14
                  else "Nachmittag" if hi < 18 else "Abend" if hi < 22 else "Nacht")
        by_tz[bucket] += int(n)
    return {"person": person, "wochentag_verteilung": by_wd,
            "tageszeit_verteilung": by_tz,
            "gesamt": sum(by_wd.values())}


async def _kontext_um(db: AsyncSession, photo_id: int, radius_tage: int = 1,
                      max_ergebnisse: int = 30, acl: Optional[list] = None) -> dict:
    """Was war um dieses Foto herum? Fotos vom gleichen Tag ±N Tage, gleicher Ort,
    Personen die dabei waren. Für 'was war noch bei diesem Foto', 'zeig mir mehr
    aus diesem Ausflug'."""
    anchor = await db.get(Photo, int(photo_id))
    if not anchor or not anchor.taken_at:
        return {"treffer": 0, "hinweis": "Ankerfoto hat kein Datum."}
    from datetime import timedelta as _td
    lo = anchor.taken_at - _td(days=max(0, int(radius_tage)))
    hi = anchor.taken_at + _td(days=max(1, int(radius_tage)))
    conds = [Photo.taken_at >= lo, Photo.taken_at <= hi,
             Photo.is_trashed == False, Photo.id != anchor.id] + list(acl or [])  # noqa: E712
    if anchor.city:
        conds.append(Photo.city == anchor.city)
    rows = (await db.execute(
        select(Photo).where(*conds).order_by(Photo.taken_at).limit(int(max_ergebnisse))
    )).scalars().all()
    return {"anker_id": anchor.id,
            "anker_datum": str(anchor.taken_at)[:10],
            "anker_ort": anchor.city,
            "treffer": len(rows),
            "fotos": await _fused_records(db, rows)}


async def _aehnliche_szenen(db: AsyncSession, photo_id: int, limit: int = 15,
                            acl: Optional[list] = None) -> dict:
    """Visuell ähnliche Fotos via pgvector cosine über photo.embedding.
    Für 'zeig ähnliche', 'gibt es weitere Fotos wie diese'."""
    anchor = await db.get(Photo, int(photo_id))
    if not anchor or anchor.embedding is None:
        return {"treffer": 0, "hinweis": "Anker hat kein Embedding."}
    dist = Photo.embedding.cosine_distance(anchor.embedding)
    conds = [Photo.id != anchor.id, Photo.embedding.isnot(None),
             Photo.is_trashed == False, Photo.status == PhotoStatus.done,   # noqa: E712
             dist < 0.35] + list(acl or [])
    rows = (await db.execute(
        select(Photo).where(*conds).order_by(dist).limit(int(limit))
    )).scalars().all()
    return {"anker_id": anchor.id, "treffer": len(rows),
            "fotos": await _fused_records(db, rows)}


async def _birthday_date(db: AsyncSession, person: Optional[str], alter=None) -> dict:
    """Exact date a person reached a given age, from the STORED birthdate. Deterministic
    (no guessing from photos) → answers 'X. Geburtstag', 'wie alt war X …'."""
    from datetime import timedelta
    if not person or not person.strip():
        return {"hat_geburtsdatum": False, "hinweis": "Kein Personenname angegeben."}
    p = (await db.execute(
        select(Person).where(_strict_name(person),
                             Person.birthdate.isnot(None)).limit(1)
    )).scalar_one_or_none()
    if not p or not p.birthdate:
        return {"hat_geburtsdatum": False,
                "hinweis": f"Für {person} ist kein Geburtsdatum hinterlegt. "
                           f"Du kannst es unter Personen → {person} → Geburtsdatum eintragen."}
    bd = p.birthdate
    out: dict = {"hat_geburtsdatum": True, "name": p.name, "geburtsdatum": bd.isoformat()}
    if alter is not None:
        try:
            try:
                target = bd.replace(year=bd.year + int(alter))
            except ValueError:        # 29. Feb → 28. Feb
                target = bd.replace(year=bd.year + int(alter), day=28)
            out["alter"] = int(alter)
            out["datum"] = target.isoformat()
            out["datum_von"] = (target - timedelta(days=10)).isoformat()
            out["datum_bis"] = (target + timedelta(days=10)).isoformat()
        except Exception:
            pass
    return out


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
            .where(_strict_name(person))
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
            select(Person.id).where(_strict_name(person)))).all()]
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


async def _action_set_rating(db: AsyncSession, settings: dict, args: dict) -> dict:
    """Setzt die Sternebewertung (1–5) für ein Foto oder alle passenden Fotos."""
    from sqlalchemy import update as _upd
    bewertung = int(args.get("bewertung") or 0)
    if not 1 <= bewertung <= 5:
        return {"ok": False, "info": "Bewertung muss 1–5 sein."}
    foto_id = args.get("foto_id")
    if foto_id:
        ids = [int(foto_id)]
    else:
        ids = await _resolve_action_photo_ids(db, settings, args, limit=500)
    if not ids:
        return {"ok": False, "info": "Keine passenden Fotos gefunden."}
    await db.execute(_upd(Photo).where(Photo.id.in_(ids)).values(user_rating=bewertung))
    await db.commit()
    return {"ok": True, "anzahl": len(ids), "bewertung": bewertung}


async def _action_add_to_album(db: AsyncSession, settings: dict, args: dict,
                               context_ids: list) -> dict:
    """Fügt Fotos zu einem BESTEHENDEN Album hinzu (per Name oder ID)."""
    from app.models.album import Album, AlbumPhoto
    album_name = (args.get("album_name") or "").strip()
    album_id = args.get("album_id")
    if album_id:
        album = await db.get(Album, int(album_id))
    elif album_name:
        album = (await db.execute(
            select(Album).where(Album.name.ilike(f"%{album_name}%")).limit(1)
        )).scalar_one_or_none()
    else:
        return {"ok": False, "info": "Album-Name oder Album-ID erforderlich."}
    if not album:
        return {"ok": False, "info": f"Album '{album_name}' nicht gefunden."}
    # Fotos: bevorzuge context_ids (letzte Suchergebnisse), sonst Suche
    if context_ids and not any(args.get(k) for k in ("suchbegriff", "person", "person2", "ort")):
        ids = list(context_ids)
    else:
        ids = await _resolve_action_photo_ids(db, settings, args, limit=2000)
    if not ids:
        return {"ok": False, "info": "Keine passenden Fotos gefunden."}
    existing = {r[0] for r in (await db.execute(
        select(AlbumPhoto.photo_id).where(AlbumPhoto.album_id == album.id,
                                          AlbumPhoto.photo_id.in_(ids)))).all()}
    max_order = await db.scalar(
        select(func.max(AlbumPhoto.sort_order)).where(AlbumPhoto.album_id == album.id)) or 0
    new_ids = [i for i in ids if i not in existing]
    for i, pid in enumerate(new_ids):
        db.add(AlbumPhoto(album_id=album.id, photo_id=pid, sort_order=max_order + i + 1))
    await db.commit()
    return {"ok": True, "album_id": album.id, "album_name": album.name,
            "hinzugefuegt": len(new_ids), "bereits_drin": len(existing)}


async def _library_status(db: AsyncSession, acl: list) -> dict:
    """Bibliotheks-/Verarbeitungsstatus — STRIKT auf die Fotos begrenzt, die der Nutzer
    sehen darf (acl = photo_conditions(user)). Ein eingeschränktes Konto sieht nur die
    Zahlen seines eigenen Umfangs, nie die der Gesamtbibliothek."""
    from app.models.photo import Photo, PhotoStatus
    from sqlalchemy import or_
    live = [Photo.is_trashed == False, *acl]  # noqa: E712

    async def c(*conds) -> int:
        return int(await db.scalar(select(func.count()).where(*live, *conds)) or 0)

    done = await c(Photo.status == PhotoStatus.done)
    videos = await c(Photo.is_video == True, Photo.status == PhotoStatus.done)  # noqa: E712
    no_desc_img = await c(Photo.is_video == False, Photo.status == PhotoStatus.done,  # noqa: E712
                          or_(Photo.description.is_(None), Photo.description == ""))
    no_desc_vid = await c(Photo.is_video == True, Photo.status == PhotoStatus.done,  # noqa: E712
                          or_(Photo.description.is_(None), Photo.description == ""))
    in_progress = await c(Photo.status.notin_([PhotoStatus.done, PhotoStatus.error]))
    errors = await c(Photo.status == PhotoStatus.error)
    min_date = await db.scalar(select(func.min(Photo.taken_at)).where(*live))
    max_date = await db.scalar(select(func.max(Photo.taken_at)).where(*live))
    return {
        "fotos_gesamt": done, "bilder": done - videos, "videos": videos,
        "in_verarbeitung": in_progress, "fehler": errors,
        "ohne_beschreibung_bilder": no_desc_img, "ohne_beschreibung_videos": no_desc_vid,
        "aeltestes_datum": min_date.date().isoformat() if min_date else None,
        "neuestes_datum": max_date.date().isoformat() if max_date else None,
    }


async def _ops_status(db: AsyncSession) -> dict:
    """Betriebs-/Leitstand-Status (system-weit) — NUR für Administratoren aufrufen
    (Gating passiert im Dispatcher). Queue-Tiefen, Worker-Liveness, globaler Backlog,
    grobe Restzeit-Schätzung."""
    from app.models.photo import Photo, PhotoStatus
    from sqlalchemy import or_
    from app.core.config import get_settings
    import asyncio as _a

    queues: dict = {}
    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(get_settings().redis_url)
        for q in ("cpu", "gpu", "scan", "video", "celery"):
            queues[q] = int(await r.llen(q))
        await r.aclose()
    except Exception as e:
        queues = {"fehler": str(e)[:80]}

    workers: dict = {}
    try:
        from app.worker.celery_app import celery_app

        def _ping():
            return celery_app.control.inspect(timeout=1.5).ping() or {}
        pong = await _a.get_running_loop().run_in_executor(None, _ping)
        workers = {name: "aktiv" for name in pong.keys()} or {"status": "keine Antwort"}
    except Exception as e:
        workers = {"status": f"unbekannt ({str(e)[:60]})"}

    async def c(*conds) -> int:  # global, kein acl (Admin)
        return int(await db.scalar(select(func.count()).where(Photo.is_trashed == False, *conds)) or 0)  # noqa: E712

    # "Offen" = wirklich noch retry-fähig: ai_error=false. Sonst zählt der Leitstand
    # ewig die Medien mit, bei denen der Provider damals gescheitert ist und die vom
    # Remote-Claim gar nicht mehr angeboten werden (siehe remote.py claim-Filter).
    no_desc_img = await c(Photo.is_video == False, Photo.status == PhotoStatus.done,  # noqa: E712
                          Photo.ai_error == False,                                    # noqa: E712
                          or_(Photo.description.is_(None), Photo.description == ""))
    no_desc_vid = await c(Photo.is_video == True, Photo.status == PhotoStatus.done,   # noqa: E712
                          Photo.ai_error == False,                                    # noqa: E712
                          or_(Photo.description.is_(None), Photo.description == ""))
    # ai_error=true → früher versucht, gescheitert. Retry über /reset-ai-errors möglich.
    failed_desc_img = await c(Photo.is_video == False, Photo.ai_error == True)        # noqa: E712
    failed_desc_vid = await c(Photo.is_video == True, Photo.ai_error == True)         # noqa: E712
    video_faces_open = await c(Photo.is_video == True, Photo.faces_scanned == False)  # noqa: E712
    errors = await c(Photo.status == PhotoStatus.error)

    gpu_q = queues.get("gpu") if isinstance(queues.get("gpu"), int) else 0
    eta = {
        "gpu_gesichter": round((gpu_q or 0) * 28 / 4 / 60),      # ~28s/Video, ~4 parallel
        "bild_beschreibungen": round(no_desc_img * 15 / 60),     # ~15s/Bild (1 Mac-Worker)
        "video_beschreibungen": round(no_desc_vid * 45 / 60),    # ~45s/Video (1 Mac-Worker)
    }
    return {
        "queues": queues, "worker": workers,
        "backlog": {"bilder_ohne_beschreibung": no_desc_img,
                    "videos_ohne_beschreibung": no_desc_vid,
                    "bilder_beschreibung_fehlgeschlagen": failed_desc_img,
                    "videos_beschreibung_fehlgeschlagen": failed_desc_vid,
                    "videos_ohne_gesichtsscan": video_faces_open,
                    "fehlerhafte_medien": errors},
        "restzeit_schaetzung_minuten": eta,
        "hinweis_restzeit": ("Grobe Schätzung aus typischen Durchsätzen — Bild- und "
                             "Video-Beschreibungen laufen parallel auf getrennten Workern; "
                             "reale Zeiten schwanken je nach Auslastung."),
    }


async def _recap(db: AsyncSession, medientyp, jahr_von, jahr_bis, person, datum_von, datum_bis,
                 ort, acl: list) -> dict:
    """Aggregat-Zusammenfassung für 'erzähl mir von…'/Rückblick: Anzahl, Zeitspanne,
    häufigste Orte, wer dabei war, Beispiel-Beschreibungen — plus die passenden Foto-IDs
    (für die Galerie). Streng ACL-gescoped."""
    from sqlalchemy import func as _f
    from app.models.photo import Photo as _P, PhotoStatus as _S
    conds = _filter_conditions(medientyp, jahr_von, jahr_bis, person, datum_von, datum_bis, None, ort)
    base = [_P.status == _S.done, _P.is_trashed == False, _P.thumb_small.isnot(None), *conds, *acl]  # noqa: E712
    row = (await db.execute(select(
        _f.count().label("total"),
        _f.count().filter(_P.is_video == True).label("videos"),                    # noqa: E712
        _f.min(_P.taken_at).label("dmin"), _f.max(_P.taken_at).label("dmax"),
    ).where(*base))).one()
    total = int(row.total or 0)
    if not total:
        return {"anzahl": 0}
    place_col = _f.coalesce(_P.city, _P.country, _P.location_name)
    places = (await db.execute(select(place_col, _f.count()).where(*base, place_col.isnot(None))
              .group_by(place_col).order_by(_f.count().desc()).limit(8))).all()
    acc_sub = select(_P.id).where(*base)
    ppl = (await db.execute(select(Person.name, _f.count(_f.distinct(Face.photo_id)).label("n"))
           .join(Face, Face.person_id == Person.id)
           .where(Face.photo_id.in_(acc_sub), _f.length(_f.coalesce(Person.name, "")) > 0,
                  Person.is_hidden == False)   # noqa: E712  keine versteckten Personen im Rückblick
           .group_by(Person.name).order_by(_f.count(_f.distinct(Face.photo_id)).desc()).limit(8))).all()
    descs = (await db.execute(select(_P.description).where(
        *base, _P.description.isnot(None), _P.description != "").order_by(_P.taken_at).limit(6))).scalars().all()
    ids = (await db.execute(select(_P.id).where(*base).order_by(_P.taken_at).limit(500))).scalars().all()
    videos = int(row.videos or 0)
    return {
        "anzahl": total, "bilder": total - videos, "videos": videos,
        "von": row.dmin.date().isoformat() if row.dmin else None,
        "bis": row.dmax.date().isoformat() if row.dmax else None,
        "top_orte": [{"ort": p[0], "anzahl": p[1]} for p in places],
        "top_personen": [{"name": p[0], "anzahl": p[1]} for p in ppl],
        "beispiel_beschreibungen": [(d or "")[:200] for d in descs],
        "_ids": list(ids),   # intern: für die Galerie, nicht an das LLM
    }


async def _create_highlight_action(db: AsyncSession, thema, person, jahr, album_id, season, user) -> dict:
    """Erstellt ein Highlight-Video (Slideshow) und reiht das Rendern ein. Bewusst OHNE
    KI-Clips (ai_clips=False) → keine fal.ai-Kosten aus dem Chat. Dauert einige Minuten."""
    from app.models.highlight import Highlight, HighlightStatus
    from app.services.highlights import MOTTOS
    valid = {m["motto"] for m in MOTTOS}
    labels = {m["motto"]: m["label"] for m in MOTTOS}
    if thema not in valid:
        return {"fehler": f"Unbekanntes Thema: {thema}"}
    pid = None
    if person and person.strip():
        row = (await db.execute(select(Person.id, Person.name).where(
            _strict_name(person)).limit(1))).first()
        if not row:
            return {"fehler": f"Person '{person}' nicht gefunden."}
        pid = row[0]
    params: dict = {"duration_sec": 60.0, "ai_clips": False}
    if pid:
        params["person_id"] = pid
    if jahr:
        params["year"] = int(jahr)
    if album_id:
        params["album_id"] = int(album_id)
    if season:
        params["season"] = season
    title = labels.get(thema, "Highlight")
    if pid and person:
        title = f"{person.strip()} — {title}"
    h = Highlight(title=title, motto=thema, duration_sec=60.0, params=params,
                  status=HighlightStatus.pending, created_by=getattr(user, "id", None))
    db.add(h)
    await db.commit()
    await db.refresh(h)
    try:
        from app.worker.tasks import render_highlight_task
        render_highlight_task.delay(h.id)
    except Exception:
        pass
    return {"ok": True, "highlight_id": h.id, "titel": title,
            "hinweis": "Wird erstellt — das dauert ein paar Minuten, danach unter Highlights sichtbar."}


async def _resolve_view(db: AsyncSession, ziel: str, name: Optional[str], user) -> dict:
    """Löst ein Navigations-Ziel in einen App-Pfad auf (Phase 3: Ansichten steuern).
    Übersichten direkt; bestimmte Person/Album/Reise per Name → deren Deep-Link.
    ACL: Personen über visible_person_subquery, Leitstand nur für Admins."""
    from app.core.access import _is_unrestricted
    z = (ziel or "").lower()
    overviews = {"personen": "/people", "alben": "/albums", "reisen": "/trips",
                 "karte": "/map", "highlights": "/highlights", "start": "/start"}
    if z in overviews:
        return {"navigate": overviews[z]}
    if z == "leitstand":
        return {"navigate": "/leitstand"} if _is_unrestricted(user) else \
               {"kein_zugriff": True, "hinweis": "Der Leitstand ist nur für Administratoren."}
    if not (name or "").strip():
        return {"fehler": "Für eine bestimmte Person/Album/Reise brauche ich einen Namen."}
    if z == "person":
        from app.models.person import Person
        from app.core.access import visible_person_subquery
        q = select(Person.id, Person.name).where(
            _strict_name(name), Person.is_hidden == False)  # noqa: E712
        vps = visible_person_subquery(user)
        if vps is not None:
            q = q.where(Person.id.in_(vps))
        row = (await db.execute(q.limit(1))).first()
        return {"navigate": f"/people?person={row[0]}", "name": row[1]} if row else \
               {"fehler": f"Person '{name}' nicht gefunden."}
    if z in ("album", "reise"):
        from app.models.album import Album, AlbumPhoto
        from app.core.access import photo_conditions
        acl = photo_conditions(user)
        q = select(Album.id, Album.name).where(Album.name.ilike(f"%{name.strip()}%"))
        if acl:
            # Eingeschränktes Konto: nur Alben, die MINDESTENS ein für den Nutzer sichtbares
            # Foto enthalten — sonst würden fremde Album-Namen/-IDs geleakt.
            q = q.where(Album.id.in_(
                select(AlbumPhoto.album_id).join(Photo, Photo.id == AlbumPhoto.photo_id).where(*acl)))
        row = (await db.execute(q.limit(1))).first()
        if not row:
            return {"fehler": f"{'Reise' if z == 'reise' else 'Album'} '{name}' nicht gefunden."}
        path = f"/trips?trip={row[0]}" if z == "reise" else f"/albums?album={row[0]}"
        return {"navigate": path, "name": row[1]}
    return {"fehler": "Unbekanntes Ziel."}


async def _build_intents(db: AsyncSession, search_args: dict, nav_target: Optional[str]) -> list:
    """Erstellt strukturierte Intent-Objekte aus den Tool-Call-Argumenten des letzten Suchlaufs.
    Gibt 0–2 Intent-Dicts zurück, die das iOS/Web-Frontend direkt als Filter anwenden kann.
    Phase 1: filter_gallery + filter_map (person_id, date range, media type).
    """
    if not search_args and not nav_target:
        return []

    intents: list = []

    # filter_gallery Intent: strukturierte Galerie-Filter aus suche_fotos-Argumenten.
    person_name = search_args.get("person") or ""
    datum_von = search_args.get("datum_von") or ""
    datum_bis = search_args.get("datum_bis") or ""
    jahr_von = search_args.get("jahr_von")
    jahr_bis = search_args.get("jahr_bis")
    medientyp = search_args.get("medientyp") or ""

    # Personenname → ID auflösen (für typisierte Intents brauchen wir die ID)
    resolved_person_id: Optional[int] = None
    if person_name.strip():
        row = (await db.execute(
            select(Person.id).where(_strict_name(person_name))
            .limit(1)
        )).first()
        if row:
            resolved_person_id = row[0]

    # Jahresfilter → ISO-Datum konvertieren wenn kein explizites datum_von/bis
    if not datum_von and jahr_von:
        datum_von = f"{int(jahr_von)}-01-01"
    if not datum_bis and jahr_bis:
        datum_bis = f"{int(jahr_bis)}-12-31"

    # media_type normalisieren
    mt = medientyp.lower()
    media_type_norm: Optional[str] = None
    if mt in ("video", "videos"):
        media_type_norm = "video"
    elif mt in ("bild", "bilder", "foto", "fotos", "image", "images"):
        media_type_norm = "photo"

    has_gallery_filter = any([resolved_person_id, datum_von, datum_bis, media_type_norm])
    if has_gallery_filter:
        intent: dict = {"type": "filter_gallery"}
        if resolved_person_id:
            intent["person_id"] = resolved_person_id
        if datum_von:
            intent["date_from"] = datum_von
        if datum_bis:
            intent["date_to"] = datum_bis
        if media_type_norm:
            intent["media_type"] = media_type_norm
        intents.append(intent)

    # filter_map Intent: wenn Personen- oder Datumsfilter vorhanden, auch die Karte filtern.
    # (Ort-Filter macht auf der Karte wenig Sinn, da die Karte bereits geografisch ist.)
    if resolved_person_id or datum_von or datum_bis:
        map_intent: dict = {"type": "filter_map"}
        if resolved_person_id:
            map_intent["person_id"] = resolved_person_id
        if datum_von:
            map_intent["date_from"] = datum_von
        if datum_bis:
            map_intent["date_to"] = datum_bis
        intents.append(map_intent)

    # navigate Intent: falls oeffne_ansicht einen Pfad geliefert hat.
    if nav_target:
        intents.append({"type": "navigate", "route": nav_target})

    return intents


async def _gemini_agent(message: str, history: list, settings: dict, db: AsyncSession,
                        user=None, context_ids: Optional[List[int]] = None) -> dict:
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
        "person3": {"type": "string", "description": "DRITTE Person, die GEMEINSAM mit person und person2 auf dem Foto sein muss. Für 'Lea mit Karin und Wolfgang'."},
        "person4": {"type": "string", "description": "VIERTE Person, gemeinsam mit person, person2, person3. Für Gruppenfotos mit 4 Namen."},
        "ort": {"type": "string", "description": "Ortsfilter (Stadt, Region ODER Land), z. B. ort='Türkei', ort='Antalya', ort='Köln'. Nutze das IMMER bei Ortsangaben ('in der Türkei', 'in Köln'). Für Länder den deutschen Landesnamen verwenden."},
        "medientyp": {"type": "string", "enum": ["bild", "video", "beide"],
                      "description": "Nur Bilder, nur Videos, oder beide. WICHTIG: fragt der Nutzer nach Videos → 'video', nach Bildern/Fotos → 'bild'."},
        "jahr_von": {"type": "integer", "description": "frühestes Jahr (inkl.), z. B. 2018"},
        "jahr_bis": {"type": "integer", "description": "spätestes Jahr (inkl.), z. B. 2020"},
        "datum_von": {"type": "string", "description": "Frühestes Datum (inkl.) als YYYY-MM-DD. Für konkrete Ereignisse/Feiertage rechne den Zeitraum SELBST aus, z. B. Ostern 2022 → datum_von='2022-04-15', datum_bis='2022-04-18'; Weihnachten 2021 → 2021-12-24..2021-12-26."},
        "datum_bis": {"type": "string", "description": "Spätestes Datum (inkl.) als YYYY-MM-DD."},
    }
    _kontext_prop = {
        "kontext_filtern": {
            "type": "boolean",
            "description": "Wenn true: nur innerhalb der IDs des LETZTEN Suchergebnisses suchen/filtern "
                           "(für Folgefragen wie 'davon nur Videos', 'daraus die besten', 'mach ein Album '  "
                           "daraus'). Setze das, wenn der Nutzer 'diese', 'davon', 'daraus', 'die Ergebnisse' sagt.",
        }
    } if context_ids else {}
    tool = {"function_declarations": [
        {
            "name": "suche_fotos",
            "description": "Durchsucht die Sammlung semantisch + nach Person/Ort/Tag und liefert passende "
                           "Medien mit Beschreibung, erkannten Personen, Tags, Datum, Ort. Mit Filtern für "
                           "Medientyp (Bild/Video) und Jahr.",
            "parameters": {"type": "object", "properties": {
                "suchbegriff": {"type": "string", "description": "Wonach gesucht wird, z. B. 'Günter im Garten', 'Strand'"},
                **_filter_props, **_kontext_prop,
            }, "required": ["suchbegriff"]},
        },
        {
            "name": "zaehle_fotos",
            "description": "Liefert die EXAKTE Anzahl passender Medien (für 'wie viele …'-Fragen). "
                           "Filtert nach Medientyp, Jahr und optional Person.",
            "parameters": {"type": "object", "properties": {
                "person": {"type": "string", "description": "optionaler Personenname, z. B. 'Lea Marie Nimtz'"},
                **_filter_props, **_kontext_prop,
            }},
        },
        {
            "name": "zeitliche_eckdaten",
            "description": "Liefert das FRÜHESTE und SPÄTESTE Foto-Datum für eine Person (optional zwei "
                           "Personen GEMEINSAM auf einem Foto). Nutze das für 'wann habe ich X das erste "
                           "Mal getroffen/gesehen', 'seit wann kenne ich X', 'wann zuletzt …' — die normale "
                           "Suche ist nach Relevanz sortiert und verpasst das wirklich früheste/späteste Foto. "
                           "MIT suchbegriff filtert auf Fotos, deren Beschreibung die Wörter enthält — für "
                           "'wann lernte X laufen' setze person='X', suchbegriff='laufen erste Schritte krabbeln stehen' "
                           "→ liefert das früheste passende Datum.",
            "parameters": {"type": "object", "properties": {
                "person": {"type": "string", "description": "Name der Person (Pflicht), z. B. 'Anja'"},
                "person2": {"type": "string", "description": "Optional: zweite Person, die GEMEINSAM mit 'person' auf demselben Foto sein muss — z. B. der Nutzer selbst bei 'wann habe ICH X getroffen'."},
                "suchbegriff": {"type": "string", "description": "Optional: Wörter, die in der Foto-Beschreibung vorkommen müssen (ODER-verknüpft). Für Meilenstein-Fragen: 'laufen erste Schritte' o. Ä."},
                "medientyp": _filter_props["medientyp"], "jahr_von": _filter_props["jahr_von"], "jahr_bis": _filter_props["jahr_bis"],
            }, "required": ["person"]},
        },
        {
            "name": "geburtstag_datum",
            "description": "Liefert das EXAKTE Datum, an dem eine Person ein Alter erreicht (aus dem "
                           "hinterlegten Geburtsdatum: Geburtsdatum + Jahre) plus ein Suchfenster "
                           "(datum_von/datum_bis). Nutze das für 'X. Geburtstag', 'wann wurde X N', "
                           "'wie alt war X im Jahr Y'. NIE selbst ein Datum/Alter raten. Ist kein "
                           "Geburtsdatum hinterlegt, kommt hat_geburtsdatum=false zurück — dann ehrlich sagen.",
            "parameters": {"type": "object", "properties": {
                "person": {"type": "string", "description": "Name der Person (Pflicht)"},
                "alter": {"type": "integer", "description": "Das Alter bzw. der Geburtstag, z. B. 40 für '40. Geburtstag'"},
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
        {
            "name": "personen_zusammenhang",
            "description": "Wer war am häufigsten MIT einer Person zusammen auf Fotos? Liefert "
                           "Top-N-Kontakte mit Anzahl gemeinsamer Fotos. Für Fragen wie 'mit wem "
                           "ist Lea am häufigsten', 'wer sind Anjas engste Kontakte', 'wer ist immer "
                           "bei Marcus dabei'.",
            "parameters": {"type": "object", "properties": {
                "person": {"type": "string", "description": "Name der Person (Pflicht)"},
                "top": {"type": "integer", "description": "Wie viele Top-Kontakte, Default 8"},
            }, "required": ["person"]},
        },
        {
            "name": "orte_von_person",
            "description": "Wo war eine Person am häufigsten? Aggregate (Stadt, Land, Anzahl Fotos, "
                           "erstes+letztes Datum). Für 'wo war Lea am meisten', 'welche Länder haben "
                           "wir besucht mit Anja', 'welche Städte kennt Marcus'.",
            "parameters": {"type": "object", "properties": {
                "person": {"type": "string", "description": "Name der Person (Pflicht)"},
                "top": {"type": "integer", "description": "Wie viele Top-Orte, Default 12"},
            }, "required": ["person"]},
        },
        {
            "name": "alltag_muster",
            "description": "Wochentag- und Tageszeit-Verteilung der Fotos einer Person. Für "
                           "'wann sehe ich Lea meistens', 'sind unsere Fotos eher Wochenende', "
                           "'zu welcher Tageszeit machen wir Fotos'.",
            "parameters": {"type": "object", "properties": {
                "person": {"type": "string", "description": "Name der Person (Pflicht)"},
            }, "required": ["person"]},
        },
        {
            "name": "kontext_um_foto",
            "description": "Was war RUND UM ein Foto herum? Fotos vom selben Zeitraum (±N Tage) und "
                           "möglichst am selben Ort. Für 'was war noch bei diesem Foto', 'zeig mehr "
                           "aus dem Tag', 'was ist noch aus dem Ausflug'.",
            "parameters": {"type": "object", "properties": {
                "photo_id": {"type": "integer", "description": "ID des Ankerfotos (Pflicht)"},
                "radius_tage": {"type": "integer", "description": "±N Tage um das Ankerfoto, Default 1"},
                "max_ergebnisse": {"type": "integer", "description": "Obergrenze der Treffer, Default 30"},
            }, "required": ["photo_id"]},
        },
        {
            "name": "aehnliche_szenen",
            "description": "Visuell ähnliche Fotos zu einem gegebenen Foto (via Bild-Embedding). "
                           "Für 'zeig ähnliche', 'weitere Fotos wie dieses', 'was sieht so aus wie #123'.",
            "parameters": {"type": "object", "properties": {
                "photo_id": {"type": "integer", "description": "ID des Ankerfotos (Pflicht)"},
                "limit": {"type": "integer", "description": "Max Treffer, Default 15"},
            }, "required": ["photo_id"]},
        },
        {
            "name": "bibliothek_status",
            "description": "Status der EIGENEN Bibliothek des Nutzers: Anzahl Fotos/Bilder/Videos, "
                           "wie viele noch in Verarbeitung sind, Fehler, wie viele noch keine KI-"
                           "Beschreibung haben, ältestes/neuestes Datum. Nutze das für 'wie viele Fotos "
                           "habe ich', 'wie viele werden noch verarbeitet', 'wie viele ohne Beschreibung'. "
                           "Zeigt ausschließlich den Umfang, den der Nutzer sehen darf.",
            "parameters": {"type": "object", "properties": {}},
        },
        {
            "name": "leitstand_status",
            "description": "Betriebs-/Leitstand-Status des SERVERS: Queue-Tiefen (cpu/gpu/scan/video), "
                           "ob die Worker laufen, der gesamte Verarbeitungs-Backlog und eine grobe "
                           "Restzeit-Schätzung. Nutze das für 'wie voll ist die Queue', 'laufen die "
                           "Worker', 'wie lange dauert die Verarbeitung noch', 'Leitstand', 'Auslastung'. "
                           "NUR für Administratoren — kommt kein_zugriff zurück, ist der Nutzer nicht berechtigt.",
            "parameters": {"type": "object", "properties": {}},
        },
        {
            "name": "oeffne_ansicht",
            "description": "Navigiert zu einer ANSICHT/Seite der App, wenn der Nutzer dorthin WILL "
                           "(nicht nur Fotos filtern). Für Übersichten: ziel='personen'|'alben'|'reisen'"
                           "|'karte'|'highlights'|'start'|'leitstand'. Für eine BESTIMMTE Person/Reise/"
                           "Album zusätzlich name= (z. B. 'öffne Anjas Seite' → ziel='person', name='Anja'; "
                           "'zeig unsere Kroatien-Reise' → ziel='reise', name='Kroatien'; 'öffne das Album "
                           "Sommer 2023' → ziel='album', name='Sommer 2023'). Für reines Fotos-Anzeigen "
                           "NICHT nutzen — dafür suche_fotos. Bestätige danach kurz, wohin du navigierst.",
            "parameters": {"type": "object", "properties": {
                "ziel": {"type": "string", "enum": ["personen", "alben", "reisen", "karte", "highlights",
                                                    "start", "leitstand", "person", "album", "reise"]},
                "name": {"type": "string", "description": "Name der Person/Reise/des Albums (nur bei ziel person/album/reise)"},
            }, "required": ["ziel"]},
        },
        {
            "name": "rueckblick",
            "description": "Liefert eine ZUSAMMENFASSUNG/ein Aggregat über einen Zeitraum, Ort oder eine "
                           "Person: Anzahl Fotos/Videos, Zeitspanne (von–bis), häufigste Orte, wer dabei "
                           "war (Top-Personen) und Beispiel-Beschreibungen. Nutze das für 'erzähl mir von …', "
                           "'wie war unser Urlaub in X', 'Rückblick 2023', 'fass den Sommer zusammen', 'wo "
                           "war ich überall', 'wen sehe ich am häufigsten'. Schreibe daraus eine kurze, warme "
                           "ERZÄHLUNG (kein reines Aufzählen) und nenne konkrete Orte/Personen/Zeiträume.",
            "parameters": {"type": "object", "properties": {
                "person": {"type": "string", "description": "optional: nur Fotos MIT dieser Person"},
                **_filter_props,
            }},
        },
        {
            "name": "highlight_erstellen",
            "description": "Erstellt ein Highlight-VIDEO (Slideshow, Rendern dauert ein paar Minuten). Für "
                           "'mach/erstell ein Video/Highlight von …'. thema wählt die Vorlage: 'person_year' "
                           "(eine Person in EINEM Jahr → + person + jahr), 'person_years' (eine Person im Laufe "
                           "der Jahre — auch für 'wie hat sich X verändert' → + person), 'year_review' "
                           "(Jahresrückblick → + jahr), 'through_the_years' (quer durch alle Jahre), 'season' "
                           "(Jahreszeit/Feiertag → + season), 'newest_50', 'most_favorited', 'top_rated', "
                           "'album_highlight'/'trip' (aus einem Album → + album_id). Für ein Video zu einem "
                           "ORT/einer Reise (z. B. 'Kroatien-Urlaub'): lege ZUERST mit album_erstellen ein "
                           "Album an und rufe DANN highlight_erstellen mit thema='trip' + dessen album_id auf.",
            "parameters": {"type": "object", "properties": {
                "thema": {"type": "string", "enum": ["person_year", "person_years", "year_review",
                                                     "through_the_years", "season", "newest_50",
                                                     "most_favorited", "top_rated", "album_highlight", "trip"]},
                "person": {"type": "string", "description": "Personenname (bei person_year/person_years)"},
                "jahr": {"type": "integer", "description": "Jahr (bei person_year/year_review)"},
                "album_id": {"type": "integer", "description": "Album-ID (bei album_highlight/trip)"},
                "season": {"type": "string", "description": "z. B. 'weihnachten', 'sommer' (bei season)"},
            }, "required": ["thema"]},
        },
        {
            "name": "bewertung_setzen",
            "description": "Setzt die Stern-Bewertung (1–5) für ein Foto oder alle passenden Fotos. "
                           "Für 'bewerte dieses Foto mit 5 Sternen', 'gib dem Bild 4 Sterne', "
                           "'markiere alle Urlaubsfotos mit 5 Sternen'. Bewertung 5=Spitze, 4=Gut, "
                           "3=OK, 2=Schwach, 1=Schlecht.",
            "parameters": {"type": "object", "properties": {
                "bewertung": {"type": "integer", "description": "1–5 Sterne"},
                "foto_id": {"type": "integer", "description": "ID eines einzelnen Fotos (wenn nur ein bestimmtes)"},
                "suchbegriff": {"type": "string", "description": "optional, welche Fotos bewertet werden"},
                "person": {"type": "string"},
                **_filter_props, **_kontext_prop,
            }, "required": ["bewertung"]},
        },
        {
            "name": "zu_album_hinzufuegen",
            "description": "Fügt Fotos zu einem BESTEHENDEN Album hinzu (kein neues Album erstellen). "
                           "Für 'füg diese zu Album X hinzu', 'pack das in mein Urlaubs-Album', 'zum Album "
                           "Sommer 2024 hinzufügen'. Wenn der Nutzer 'diese'/'die Ergebnisse'/'davon' "
                           "sagt, nutze kontext_filtern=true (letztes Suchergebnis).",
            "parameters": {"type": "object", "properties": {
                "album_name": {"type": "string", "description": "Name des bestehenden Albums (Teilname reicht)"},
                "album_id": {"type": "integer", "description": "Album-ID (wenn bekannt)"},
                "suchbegriff": {"type": "string", "description": "optional: welche Fotos"},
                "person": {"type": "string"},
                **_filter_props, **_kontext_prop,
            }},
        },
    ]}
    contents = []
    for h in (history or [])[-8:]:
        role = "user" if h.get("role") == "user" else "model"
        contents.append({"role": role, "parts": [{"text": h.get("content", "")}]})
    contents.append({"role": "user", "parts": [{"text": message}]})

    seen_ids: list = []
    nav_target: Optional[str] = None   # Ansichts-Navigation (oeffne_ansicht) → Frontend springt dorthin
    seen_recs: dict = {}   # id → fused record (description/date/place) for a rich gallery reply
    # Phase 1 Intents: sammle strukturierte Filter aus Tool-Calls → als intents[] zurückgeben
    last_search_args: dict = {}  # letzter suche_fotos/rueckblick Aufruf (für Intent-Extraktion)
    # Multimodal: send the top hits' thumbnails so Gemini can SEE them. Budget caps
    # total images across the conversation to bound token cost (chat.vision=off disables).
    vision = str(settings.get("chat.vision", "true")).lower() != "false"
    img_budget = 8
    # Identity block (who is the user + relations) so 'meine Frau' resolves without
    # a clarifying round-trip.
    from app.core.access import photo_conditions, _is_unrestricted
    acl = photo_conditions(user)                 # [] for admin/open; folder/date/person scope otherwise
    restricted = not _is_unrestricted(user)      # restricted accounts get read-only chat
    # Persona/Ton aus den Einstellungen (freundlich/lustig/proaktiv …) — vor die Identität
    # gehängt, damit der Nutzer den Charakter des Assistenten steuern kann.
    persona = (settings.get("chat.persona") or "").strip()
    persona_block = (f"\n\nPERSÖNLICHKEIT & TON (vom Nutzer vorgegeben, befolge das durchgehend, "
                     f"ohne die inhaltliche Korrektheit zu opfern): {persona[:600]}") if persona else ""
    # HEUTIGES DATUM + relative Zeitangaben: ohne "heute" kann das Modell "letzte Woche",
    # "gestern", "diesen Monat" nicht in ein Datumsfenster übersetzen und sucht dann über
    # ALLE Jahre (Bug: "Anja letzte Woche" → Bilder aus vielen Jahren). Wir liefern das
    # Datum und die exakte Umrechnungsregel mit, inkl. berechneter Wochen-Eckdaten.
    # CONTEXT_IDS: letzte Suchergebnisse — für Folgefragen ("davon", "daraus") bereitstellen.
    ctx_block = ""
    if context_ids:
        preview = context_ids[:8]
        ctx_block = (f"\n\nKONTEXT — letztes Suchergebnis: {len(context_ids)} Fotos (IDs: "
                     f"{preview}{'…' if len(context_ids) > 8 else ''}). "
                     f"Wenn der Nutzer 'diese', 'davon', 'daraus', 'die', 'sie' meint (Folgefrage auf "
                     f"die letzte Suche): setze im Tool kontext_filtern=true — dann wird NUR innerhalb "
                     f"dieser {len(context_ids)} Fotos gefiltert. Gibt es keinen Bezug auf das letzte "
                     f"Ergebnis (neue, unabhängige Suche), lasse kontext_filtern weg.")
    system_text = SYSTEM + _today_block() + ctx_block + persona_block + await _identity_context(db, settings, user)
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
                    # v1.540: Debug-Log jedes Tool-Calls im Klartext, damit wir sehen
                    # was der Agent tut und woran ein Miss liegt.
                    try:
                        from app.services.feature_log import log as _flog
                        _snip = {k: (str(v)[:80] if not isinstance(v, (int, float, bool)) else v)
                                 for k, v in list(args.items())[:10]}
                        _flog("chat", "INFO",
                              f"Tool[{c.get('name')}] args={_snip}")
                    except Exception:
                        pass
                    if c.get("name") == "zaehle_fotos":
                        if args.get("kontext_filtern") and context_ids:
                            # Zähle direkt innerhalb des Kontexts (filtere nach Medientyp etc.)
                            ctx_acl_count = list(acl) + [Photo.id.in_(context_ids)]
                            resp = await _count(db, args.get("medientyp"), args.get("jahr_von"),
                                                args.get("jahr_bis"), args.get("person"), acl=ctx_acl_count,
                                                person2=args.get("person2"), ort=args.get("ort"),
                                                datum_von=args.get("datum_von"), datum_bis=args.get("datum_bis"))
                        else:
                            resp = await _count(db, args.get("medientyp"), args.get("jahr_von"),
                                                args.get("jahr_bis"), args.get("person"), acl=acl,
                                                person2=args.get("person2"), ort=args.get("ort"),
                                                datum_von=args.get("datum_von"), datum_bis=args.get("datum_bis"))
                        contents.append({"role": "user", "parts": [{"functionResponse": {
                            "name": c["name"], "response": resp}}]})
                    elif c.get("name") == "zeitliche_eckdaten":
                        resp = await _temporal_bounds(db, args.get("person"), args.get("person2"),
                                                      args.get("medientyp"), args.get("jahr_von"),
                                                      args.get("jahr_bis"), acl=acl,
                                                      suchbegriff=args.get("suchbegriff"))
                        eids = [resp[k] for k in ("erstes_foto_id", "letztes_foto_id") if resp.get(k)]
                        seen_ids.extend(eids)
                        if eids:
                            photos = (await db.execute(select(Photo).where(Photo.id.in_(eids)))).scalars().all()
                            for rrec in await _fused_records(db, photos):
                                seen_recs.setdefault(rrec["id"], rrec)
                        contents.append({"role": "user", "parts": [{"functionResponse": {
                            "name": c["name"], "response": resp}}]})
                    elif c.get("name") == "geburtstag_datum":
                        resp = await _birthday_date(db, args.get("person"), args.get("alter"))
                        contents.append({"role": "user", "parts": [{"functionResponse": {
                            "name": c["name"], "response": resp}}]})
                    elif c.get("name") == "personen_zusammenhang":
                        resp = await _personen_zusammenhang(db, args.get("person"), int(args.get("top") or 8), acl=acl)
                        contents.append({"role": "user", "parts": [{"functionResponse": {
                            "name": c["name"], "response": resp}}]})
                    elif c.get("name") == "orte_von_person":
                        resp = await _orte_von_person(db, args.get("person"), int(args.get("top") or 12), acl=acl)
                        contents.append({"role": "user", "parts": [{"functionResponse": {
                            "name": c["name"], "response": resp}}]})
                    elif c.get("name") == "alltag_muster":
                        resp = await _alltag_muster(db, args.get("person"), acl=acl)
                        contents.append({"role": "user", "parts": [{"functionResponse": {
                            "name": c["name"], "response": resp}}]})
                    elif c.get("name") == "kontext_um_foto":
                        pid_arg = args.get("photo_id")
                        try: pid_arg = int(pid_arg) if pid_arg is not None else 0
                        except Exception: pid_arg = 0
                        resp = await _kontext_um(db, pid_arg,
                                                 int(args.get("radius_tage") or 1),
                                                 int(args.get("max_ergebnisse") or 30),
                                                 acl=acl) if pid_arg else {"treffer": 0, "hinweis": "Keine photo_id."}
                        contents.append({"role": "user", "parts": [{"functionResponse": {
                            "name": c["name"], "response": resp}}]})
                    elif c.get("name") == "aehnliche_szenen":
                        pid_arg = args.get("photo_id")
                        try: pid_arg = int(pid_arg) if pid_arg is not None else 0
                        except Exception: pid_arg = 0
                        resp = await _aehnliche_szenen(db, pid_arg,
                                                       int(args.get("limit") or 15),
                                                       acl=acl) if pid_arg else {"treffer": 0, "hinweis": "Keine photo_id."}
                        contents.append({"role": "user", "parts": [{"functionResponse": {
                            "name": c["name"], "response": resp}}]})
                    elif c.get("name") == "bibliothek_status":
                        # Streng ACL-scoped: nur der Umfang, den der Nutzer sehen darf.
                        resp = await _library_status(db, acl)
                        contents.append({"role": "user", "parts": [{"functionResponse": {
                            "name": c["name"], "response": resp}}]})
                    elif c.get("name") == "leitstand_status":
                        # System-weite Betriebsdaten NUR für unbeschränkte (Admin-)Konten.
                        if restricted:
                            resp = {"kein_zugriff": True,
                                    "hinweis": "Leitstand-/Betriebsdaten (Queue, Worker, Restzeit) "
                                               "sind nur für Administratoren einsehbar."}
                        else:
                            resp = await _ops_status(db)
                        contents.append({"role": "user", "parts": [{"functionResponse": {
                            "name": c["name"], "response": resp}}]})
                    elif c.get("name") == "oeffne_ansicht":
                        resp = await _resolve_view(db, args.get("ziel"), args.get("name"), user)
                        if resp.get("navigate"):
                            nav_target = resp["navigate"]
                        contents.append({"role": "user", "parts": [{"functionResponse": {
                            "name": c["name"], "response": resp}}]})
                    elif c.get("name") == "rueckblick":
                        resp = await _recap(db, args.get("medientyp"), args.get("jahr_von"), args.get("jahr_bis"),
                                            args.get("person"), args.get("datum_von"), args.get("datum_bis"),
                                            args.get("ort"), acl)
                        seen_ids.extend(resp.pop("_ids", []))   # Galerie zeigt die Fotos des Rückblicks
                        contents.append({"role": "user", "parts": [{"functionResponse": {
                            "name": c["name"], "response": resp}}]})
                    elif c.get("name") == "highlight_erstellen":
                        # Highlight-Erstellung = Schreib-/Render-Aktion → für eingeschränkte Konten aus.
                        if restricted:
                            resp = {"fehler": "Aktionen sind in diesem Konto nicht verfügbar."}
                        else:
                            resp = await _create_highlight_action(db, args.get("thema"), args.get("person"),
                                                                  args.get("jahr"), args.get("album_id"),
                                                                  args.get("season"), user)
                        contents.append({"role": "user", "parts": [{"functionResponse": {
                            "name": c["name"], "response": resp}}]})
                    elif c.get("name") in ("album_erstellen", "als_favorit_markieren",
                                           "bewertung_setzen", "zu_album_hinzufuegen"):
                        # Write actions stay disabled for restricted accounts (read-only chat).
                        if restricted:
                            resp = {"fehler": "Aktionen sind in diesem Konto nicht verfügbar."}
                        elif c.get("name") == "album_erstellen":
                            resp = await _action_create_album(db, settings, args)
                        elif c.get("name") == "als_favorit_markieren":
                            resp = await _action_favorite(db, settings, args)
                        elif c.get("name") == "bewertung_setzen":
                            resp = await _action_set_rating(db, settings, args)
                        else:  # zu_album_hinzufuegen
                            resp = await _action_add_to_album(db, settings, args, context_ids or [])
                        contents.append({"role": "user", "parts": [{"functionResponse": {
                            "name": c["name"], "response": resp}}]})
                    else:
                        # Intent-Tracking: letzten suche_fotos-Aufruf merken für intents[].
                        if any(args.get(k) for k in ("person", "datum_von", "datum_bis",
                                                      "jahr_von", "jahr_bis", "medientyp")):
                            last_search_args = dict(args)
                        # kontext_filtern: Folgefrage auf das letzte Suchergebnis →
                        # nur innerhalb der context_ids suchen/filtern.
                        ctx_acl = list(acl)
                        if args.get("kontext_filtern") and context_ids:
                            from sqlalchemy import and_
                            ctx_acl = list(acl) + [Photo.id.in_(context_ids)]
                        recs = await _retrieve(db, args.get("suchbegriff", ""), settings,
                                               medientyp=args.get("medientyp"),
                                               jahr_von=args.get("jahr_von"), jahr_bis=args.get("jahr_bis"),
                                               person=args.get("person"), person2=args.get("person2"),
                                               person3=args.get("person3"), person4=args.get("person4"),
                                               ort=args.get("ort"),
                                               datum_von=args.get("datum_von"), datum_bis=args.get("datum_bis"),
                                               acl=ctx_acl)
                        for rrec in recs:
                            seen_recs.setdefault(rrec["id"], rrec)
                        # GALERIE = ALLE Treffer: bei starken Struktur-Filtern (Person/Ort/
                        # Datum/Jahr) das VOLLE ID-Set liefern statt nur der ~60 Modell-
                        # Kontext-Records — behebt „findet viel zu wenig". Bei reiner
                        # Freitext-Semantik ohne Filter bleibt es bei den gerankten Records.
                        has_struct = any(args.get(k) for k in ("person", "person2", "person3", "person4",
                                          "ort", "datum_von", "datum_bis", "jahr_von", "jahr_bis"))
                        gallery_ids = [rrec["id"] for rrec in recs]
                        # Echte gesamt_anzahl: separater COUNT ohne 2000er-Cap, damit das Modell
                        # "2000 Fotos von Anja" nicht sagt, wenn es 7742 sind.
                        if args.get("kontext_filtern") and context_ids:
                            # WAR: `not ctx_acl or True` — immer True → Filter unwirksam.
                            # Jetzt: bei aktivem ctx_acl (Medientyp/Person-Filter im Kontext)
                            # zählen wir gefiltert per COUNT — sonst einfach len(context_ids).
                            if ctx_acl:
                                gesamt = await db.scalar(
                                    select(func.count()).select_from(Photo).where(
                                        Photo.id.in_(context_ids), *ctx_acl,
                                    )
                                ) or 0
                                # gallery_ids sollen auch die gefilterten sein
                                _filtered = (await db.execute(
                                    select(Photo.id).where(
                                        Photo.id.in_(context_ids), *ctx_acl,
                                    ).order_by(Photo.taken_at.desc().nullslast(), Photo.id.desc())
                                )).all()
                                full = [pid for (pid,) in _filtered]
                            else:
                                gesamt = len(context_ids)
                                full = list(context_ids)
                            gallery_ids = full
                        elif has_struct:
                            cnt_res = await _count(
                                db, args.get("medientyp"), args.get("jahr_von"), args.get("jahr_bis"),
                                args.get("person"), acl=acl,
                                person2=args.get("person2"), ort=args.get("ort"),
                                datum_von=args.get("datum_von"), datum_bis=args.get("datum_bis"),
                                person3=args.get("person3"), person4=args.get("person4"))
                            gesamt = cnt_res["anzahl"]
                            full = await _structural_ids(
                                db, args.get("medientyp"), args.get("jahr_von"), args.get("jahr_bis"),
                                args.get("person"), args.get("person2"), args.get("ort"),
                                args.get("datum_von"), args.get("datum_bis"), acl,
                                person3=args.get("person3"), person4=args.get("person4"))
                            if full:
                                gallery_ids = full
                        else:
                            gesamt = len(gallery_ids)
                        seen_ids.extend(gallery_ids)
                        contents.append({"role": "user", "parts": [{"functionResponse": {
                            "name": c["name"], "response": {"treffer": recs, "gesamt_anzahl": gesamt}}}]})
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
            # Proaktive Folge-Vorschläge: der Agent hängt optional eine letzte Zeile
            # "VORSCHLÄGE: a | b | c" an → als antippbare Chips ausliefern, aus dem
            # angezeigten Antworttext entfernen.
            suggestions: list = []
            sm = _re.search(r"(?im)^\s*VORSCHL[ÄA]GE\s*:\s*(.+)$", text)
            if sm:
                suggestions = [s.strip(" -•") for s in sm.group(1).split("|") if s.strip(" -•")][:3]
                text = text[:sm.start()].rstrip()
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
            # result_ids = VOLLES Such-Ergebnis (alle Treffer), für den Ambient-Assistenten,
            # der die Galerie darauf filtert. photo_ids = nur die zitierten Beispiele (Chat-Blase).
            intents = await _build_intents(db, last_search_args, nav_target)
            try:
                from app.services.feature_log import log as _flog2
                _flog2("chat", "INFO",
                       f"Antwort ({len(uniq)} Fotos): {(text or '')[:250]}")
            except Exception:
                pass
            return {"answer": text or "(keine Antwort)", "photo_ids": uniq,
                    "result_ids": list(dict.fromkeys(seen_ids)),
                    "suggestions": suggestions, "navigate": nav_target,
                    "intents": intents,
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
    prompt = (f"{SYSTEM}{_today_block()}\n\nGefundene Fotos (JSON):\n{ctx}\n\nFrage: {message}\n\n"
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
               provider: Optional[str] = None, user=None,
               context_ids: Optional[List[int]] = None) -> dict:
    prov = (provider or settings.get("chat.provider") or "gemini").lower()
    # v1.540: Frage in Klartext loggen — damit wir konkret sehen was ankommt.
    try:
        from app.services.feature_log import log as _flog0
        _flog0("chat", "INFO", f"Frage: {(message or '')[:300]}")
    except Exception:
        pass
    if prov == "local":
        return await _local_rag(message, settings, db, user=user)
    # Gesamt-Deadline für einen Chat-Turn — sonst kann der Agent-Loop (Retry × Tool-
    # Rounds × httpx-Backoff) 30 min laufen und der User bekommt „Konnte gerade
    # nicht antworten" nach 5 min Client-Timeout. Backend-Deckel 90 s lässt Zeit
    # für 2-3 Tool-Rounds und einen Retry.
    import asyncio as _asyncio
    try:
        return await _asyncio.wait_for(
            _gemini_agent(message, history, settings, db, user=user,
                          context_ids=context_ids or None),
            timeout=90.0)
    except _asyncio.TimeoutError:
        return {"answer": "Ich habe zu lange gebraucht — bitte formuliere die Frage "
                          "vielleicht etwas konkreter (Person, Jahr, Ort). Ich versuche's "
                          "gleich nochmal.",
                "photo_ids": [], "photos": []}
