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

_SYSTEM = (
    "Du bist ein präziser Reise-Planer. Aus der groben Beschreibung einer Reise "
    "oder Kreuzfahrt erstellst du eine strukturierte Route: ein Reisename, der "
    "Zeitraum, eine kurze Zusammenfassung und die Wegpunkte (Häfen/Städte/Stationen) "
    "in der Reihenfolge des Reiseverlaufs. Für jeden Wegpunkt gibst du ungefähre "
    "geografische Koordinaten (Breitengrad lat, Längengrad lng) aus deinem Wissen an "
    "und – falls ein Zeitraum genannt ist – ein plausibles Datum (YYYY-MM-DD), über "
    "den Zeitraum verteilt. Nenne reale, bekannte Orte. Erfinde keine Daten, wenn "
    "kein Zeitraum bekannt ist (Datum dann leer lassen)."
)


async def plan_trip(description: str, date_from: Optional[str], date_to: Optional[str],
                    settings: dict) -> dict:
    key = (settings.get("ai.gemini.api_key") or "").strip()
    if not key:
        return {"error": "Kein Gemini-API-Key hinterlegt (Einstellungen → KI)."}
    model = settings.get("ai.gemini.model", "gemini-2.5-flash")
    base = "https://generativelanguage.googleapis.com/v1beta"
    prompt = (f"Beschreibung der Reise: {description}\n"
              f"Zeitraum (Hinweis): {date_from or 'unbekannt'} bis {date_to or 'unbekannt'}\n"
              "Erstelle die strukturierte Route.")
    payload = {
        "system_instruction": {"parts": [{"text": _SYSTEM}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "response_mime_type": "application/json",
            "response_schema": _SCHEMA,
            "temperature": 0.3,
        },
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
            text = " ".join(p.get("text", "") for p in parts).strip()
            data = json.loads(text)
            # keep only well-formed waypoints
            wps = [w for w in (data.get("waypoints") or [])
                   if isinstance(w.get("lat"), (int, float)) and isinstance(w.get("lng"), (int, float))]
            data["waypoints"] = wps
            return data
    except Exception as e:
        return {"error": f"Planung fehlgeschlagen: {str(e)[:160]}"}
