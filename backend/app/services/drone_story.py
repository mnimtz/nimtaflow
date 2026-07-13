"""v1.563: Höhenprofil-Storytelling für Drohnen-Aufnahmen.

Aus drone_metadata (Höhe, Gimbal, Yaw) + Kontext (Zeitpunkt, Ort, Nachbar-
Aufnahmen) einen menschenlesbaren 1-2-Satz-Text bauen. Kein VLM-Call nötig,
alles aus Metadaten deterministisch.
"""
from typing import Optional


def _alt_bucket(m: float) -> str:
    if m < 5:   return "knapp über dem Boden"
    if m < 15:  return "wenige Meter über dem Boden"
    if m < 40:  return "aus mittlerer Höhe"
    if m < 80:  return "hoch über der Umgebung"
    if m < 130: return "in Vogelperspektive"
    if m < 250: return "aus großer Höhe"
    return "aus sehr großer Höhe"


def _gimbal_bucket(pitch: float) -> str:
    # pitch < 0 = Kamera nach unten geneigt (Standard-Drohnen-Perspektive)
    p = float(pitch or 0)
    if p < -75: return "senkrecht nach unten"
    if p < -45: return "steil nach unten"
    if p < -15: return "leicht nach unten"
    if p < 15:  return "geradeaus"
    return "leicht nach oben"


def story_for_photo(drone_meta: dict, city: Optional[str] = None,
                    country: Optional[str] = None) -> Optional[str]:
    """Ein einzelnes Drohnen-Foto → 1 Satz.
    Beispiel: 'Aufnahme aus 120 m Höhe über Palma, Kamera steil nach unten.'"""
    if not drone_meta:
        return None
    rel = drone_meta.get("relative_altitude_m")
    absa = drone_meta.get("absolute_altitude_m")
    pitch = drone_meta.get("gimbal_pitch")
    parts = []
    if rel is not None:
        parts.append(f"Aufnahme aus {int(rel)} m Höhe")
    elif absa is not None:
        parts.append(f"Aufnahme auf {int(absa)} m")
    else:
        parts.append("Luftaufnahme")
    if city or country:
        loc = ", ".join([x for x in (city, country) if x])
        parts[-1] += f" über {loc}"
    if pitch is not None:
        parts.append(f"Kamera {_gimbal_bucket(float(pitch))}")
    return ", ".join(parts) + "."


def story_for_flight(photos: list, drone_metas: list,
                     city: Optional[str] = None) -> Optional[str]:
    """Mehrere Drohnen-Aufnahmen aus demselben Flug → 2-3 Sätze mit Verlauf.
    photos: [{taken_at, id, filename}], drone_metas: passende Metadaten."""
    if not drone_metas:
        return None
    alts = [m.get("relative_altitude_m") for m in drone_metas
            if m and m.get("relative_altitude_m") is not None]
    if not alts:
        return None
    lo, hi = min(alts), max(alts)
    n = len(drone_metas)
    parts = [f"{n} Drohnenaufnahmen"]
    if city:
        parts[-1] += f" über {city}"
    parts.append(f"Höhenbereich {int(lo)}–{int(hi)} m ({_alt_bucket(hi)})")
    if hi - lo > 20:
        parts.append("mit klarem Auf-/Abstieg")
    return ", ".join(parts) + "."
