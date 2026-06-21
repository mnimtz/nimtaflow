"""AI trip planner — turn a rough free-text trip/cruise description into a
structured itinerary (named waypoints with dates + approximate coordinates) using
Gemini's structured-output mode. The coordinates come from Gemini's geographic
knowledge (ports/cities), so no external geocoding API is needed."""
import json
from typing import Optional

import httpx

_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "name": {"type": "STRING"},
        "date_from": {"type": "STRING"},   # YYYY-MM-DD
        "date_to": {"type": "STRING"},
        "summary": {"type": "STRING"},
        "waypoints": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "place": {"type": "STRING"},
                    "country": {"type": "STRING"},
                    "date": {"type": "STRING"},      # YYYY-MM-DD, best guess
                    "lat": {"type": "NUMBER"},
                    "lng": {"type": "NUMBER"},
                    "note": {"type": "STRING"},
                },
                "required": ["place", "lat", "lng"],
            },
        },
    },
    "required": ["name", "waypoints"],
}

# Type-specific routing guidance fed into the prompt so a cruise ≠ a package
# holiday ≠ a road trip.
_TYPE_HINTS = {
    "kreuzfahrt": "Es ist eine KREUZFAHRT: Wegpunkte sind die angelaufenen HÄFEN in der "
                  "tatsächlichen Fahrtreihenfolge (inkl. Start-/Zielhafen und Seetagen, "
                  "Seetage ohne Koordinaten weglassen). Erkenne Reederei und Schiff.",
    "pauschalurlaub": "Es ist ein PAUSCHALURLAUB: i. d. R. EIN Hauptort/Hotelort "
                      "(plus ggf. Anreiseflughafen und ein paar Ausflugsziele).",
    "flugreise": "Es ist eine FLUGREISE: Abflugort und Zielort(e); keine Überlandstrecke erfinden.",
    "roadtrip": "Es ist ein ROADTRIP: die Etappenorte in Fahrreihenfolge.",
    "rundreise": "Es ist eine RUNDREISE: die besuchten Orte in Reihenfolge.",
    "dienstreise": "Es ist eine DIENSTREISE: der/die Zielort(e).",
    "städtereise": "Es ist eine STÄDTEREISE: die besuchte(n) Stadt/Städte.",
}

_SYSTEM = (
    "Du bist ein präziser Reise-Planer mit Internet-Recherche. Aus der Beschreibung "
    "einer Reise erstellst du die TATSÄCHLICHE Route: Reisename, Zeitraum, kurze "
    "Zusammenfassung und die Wegpunkte (Häfen/Städte/Stationen) in der RICHTIGEN "
    "Reihenfolge mit ungefähren Koordinaten (lat, lng) und – wenn ein Zeitraum genannt "
    "ist – einem Datum (YYYY-MM-DD) je Wegpunkt.\n"
    "WICHTIG – nicht raten: Nenne die Beschreibung oft eine KONKRETE Reise (Reederei, "
    "Schiff, Veranstalter, Datum, z. B. 'AIDA … 22.-29.12.2025'). RECHERCHIERE dann mit "
    "der Google-Suche die ECHTE Route dieser konkreten Reise und gib deren reale Häfen/"
    "Stationen in der echten Reihenfolge zurück. ERFINDE KEINE Stationen. Wenn du die "
    "tatsächliche Route trotz Suche nicht sicher findest, gib nur die sicher bekannten "
    "Orte (z. B. Start-/Zielhafen) zurück und schreibe die Unsicherheit offen in "
    "'summary' — lieber wenige korrekte als viele erfundene Wegpunkte.\n"
    "Antworte AUSSCHLIESSLICH mit einem JSON-Objekt (keine Markdown-Codeblöcke, kein "
    "Text drumherum) mit den Feldern: name (string), date_from (YYYY-MM-DD), date_to "
    "(YYYY-MM-DD), summary (string), waypoints (array von {place, country, date, lat, "
    "lng, note}). lat/lng sind Pflicht je Wegpunkt."
)


def _parse_json_lenient(text: str) -> dict:
    """Grounded responses can't use response_schema, so strip any ```json fences /
    surrounding prose and parse the first {...} block."""
    t = text.strip()
    if t.startswith("```"):
        t = t.split("```", 2)[1] if "```" in t[3:] else t.lstrip("`")
        if t.lstrip().lower().startswith("json"):
            t = t.lstrip()[4:]
    start, end = t.find("{"), t.rfind("}")
    if start != -1 and end != -1 and end > start:
        t = t[start:end + 1]
    return json.loads(t)


async def plan_trip(description: str, date_from: Optional[str], date_to: Optional[str],
                    settings: dict, trip_type: Optional[str] = None) -> dict:
    key = (settings.get("ai.gemini.api_key") or "").strip()
    if not key:
        return {"error": "Kein Gemini-API-Key hinterlegt (Einstellungen → KI)."}
    model = settings.get("ai.gemini.model", "gemini-2.5-flash")
    base = "https://generativelanguage.googleapis.com/v1beta"
    type_hint = _TYPE_HINTS.get((trip_type or "").strip().lower(), "")
    prompt = (f"Beschreibung der Reise: {description}\n"
              f"Zeitraum: {date_from or 'unbekannt'} bis {date_to or 'unbekannt'}\n"
              + (f"Reiseart: {type_hint}\n" if type_hint else "")
              + "Recherchiere die tatsächliche Route und gib das JSON-Objekt zurück.")
    payload = {
        "system_instruction": {"parts": [{"text": _SYSTEM}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        # Google-Search grounding so a concrete cruise/package resolves to its REAL
        # itinerary instead of a plausible-but-wrong one. NOTE: grounding tools and
        # response_schema are mutually exclusive in the Gemini API → we ask for JSON
        # in the prompt and parse leniently. temperature 0 for factual recall.
        "tools": [{"google_search": {}}],
        "generationConfig": {"temperature": 0.0, "thinkingConfig": {"thinkingBudget": 0}},
    }
    try:
        async with httpx.AsyncClient(timeout=90) as client:
            r = None
            for attempt in range(4):
                r = await client.post(f"{base}/models/{model}:generateContent",
                                      params={"key": key}, json=payload)
                if r.status_code in (429, 500, 503) and attempt < 3:
                    import asyncio
                    await asyncio.sleep(2 ** attempt)
                    continue
                break
            if r.status_code != 200:
                return {"error": f"Gemini gerade nicht erreichbar ({r.status_code})."}
            cand = (r.json().get("candidates") or [{}])[0]
            parts = (cand.get("content") or {}).get("parts") or []
            text = " ".join(p.get("text", "") for p in parts if p.get("text")).strip()
            data = _parse_json_lenient(text)
            wps = [w for w in (data.get("waypoints") or [])
                   if isinstance(w.get("lat"), (int, float)) and isinstance(w.get("lng"), (int, float))]
            data["waypoints"] = wps
            if trip_type:
                data["trip_type"] = trip_type
            return data
    except Exception as e:
        return {"error": f"Planung fehlgeschlagen: {str(e)[:160]}"}
