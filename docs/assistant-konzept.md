# Ambient-KI-Assistent — Konzept & Phasen

> Ziel: Den bisherigen **KI-Chat (eigene Seite)** durch einen **überall präsenten, kontext-
> bewussten Assistenten** ersetzen, der die **aktuelle Ansicht steuert** statt Ergebnisse in
> einer Chat-Blase zu zeigen. Kleines Symbol unten rechts (web + iOS) → leicht transparentes
> Overlay. Fragt man in der Galerie „Wann lernte Lea laufen?", **filtert sich die Galerie**
> auf die Treffer — mit allen Galerie-Funktionen.
> **Der alte Chat-Menüpunkt fliegt raus, sobald der Assistent stabil läuft.**

## Architektur (der verbindende Trick)
„MCP nach innen": Der bestehende Tool-Calling-Motor (`chat.py`) bekommt **UI-Werkzeuge**, die
strukturierte **View-Intents** zurückgeben statt nur Text.
```
Frontend (Overlay)  ──message + KONTEXT──▶  /api/chat (erweitert)
  Kontext = { view, aktive_filter, auswahl_ids, ergebnis_set_ids, person/album }
                     ◀── { answer, intents:[…], photo_ids }
Frontend wendet intents auf die AKTUELLE Ansicht an (gemeinsamer „Ergebnis-Set + Intent"-Store)
```
- **Ergebnis-Set-Store** (z. B. Zustand/Context): hält das aktive Ergebnis-Set + letzte Intents;
  jede Ansicht (Galerie/Karte/…) abonniert ihn und rendert entsprechend.
- **Intents** (Beispiele): `filter_gallery{criteria}`, `filter_map{person,hasGps,date}`,
  `select{ids}`, `create_highlight{person,query,music,seconds}`, `create_album{name,ids|criteria}`,
  `share{ids,expires}`, `postcard{photo,text,theme}`, `navigate{route}`, `answer_only`.
- **Rückkanal für Anschlussfragen:** der Assistent sieht das aktuelle Ergebnis-Set/Auswahl →
  „und davon nur die mit Anja", „teile die drei da" funktionieren.

## Settings — eigener Bereich „Assistent"
- **Master an/aus.**
- **Pro-Ansicht-Erlaubnisse (granular):** Galerie · Karte · Personen · Reisen · Highlights · Alben
  — je an/aus (darf der Assistent dort filtern/handeln?).
- **Aktions-Stufe:** *nur lesen/filtern* ↔ *auch schreiben* (Album/Highlight/Teilen anlegen) —
  spiegelt den MCP `read | read_write`-Split.
- **KI-Backend-Wahl:** **lokal** (Ollama/integriert) ↔ **Cloud** (Gemini/…). Default lokal
  (Datenschutz). Nutzt/erweitert die bestehende `chat.provider`-Logik → `assistant.provider`.
- Optional: Position/Erscheinung des Overlays.

## Phasen
- **Ph0 — Fundament.** Schwebendes Widget (FAB + transparentes Overlay) app-weit (web); gemeinsamer
  Ergebnis-Set-Store; Kontext-Erfassung (aktuelle Ansicht); `/api/chat` gibt `photo_ids` in den
  Store → in der **Galerie** filtert sich die Ansicht. Das ist schon der „Aha".
- **Ph1 — Karte + Galerie-Intents.** `filter_gallery` (Person/Tag/Datum/Ergebnis) und `filter_map`
  (nur GPS-Punkte mit Person X). Die zwei wirkungsstärksten Flächen.
- **Ph2 — Aktionen.** `create_highlight` (Person/Motiv/Musik/Länge → Auftrag bei Highlights),
  `create_album`, `share`, `postcard` — Objekte/Jobs im Kontext anlegen.
- **Ph3 — Personen/Reisen/Wartung + Follow-ups.** Ko-Vorkommen („Lea UND Anja"), Reisen anlegen,
  Wartung (Status, Namen schreiben, Duplikate); Anschlussfragen über Ergebnis-Set/Auswahl.
- **Ph4 — iOS.** Derselbe schwebende Assistent auf iOS (nutzt denselben `/api/chat` + Intents).
- **Ph5 — Settings + alten Chat abschalten.** Granulare Erlaubnisse + KI-Backend-Wahl; wenn stabil:
  **den eigenständigen KI-Chat-Menüpunkt entfernen** (web + iOS).

## Wiederverwendung (viel liegt bereit)
- `chat.py` macht schon Tool-Calls + liefert `photo_ids`, `_identity_context` (Beziehungen),
  `zeitliche_eckdaten`, `geburtstag_datum` …
- MCP-Tools spiegeln fast alle nötigen Aktionen (suche/detail/album/teilen/highlight) → gleiche
  Logik, nur als View-Intents.
- Highlight-/Share-/Album-Pipelines existieren → Aktionen sind „nur" Verdrahtung.

## Offene Entscheidungen
- Overlay-Technik (Portal + Store) und wie „Kontext" pro Ansicht sauber bereitgestellt wird.
- Intent-Schema final (ein `intents[]`-Array in der Chat-Antwort vs. dedizierte Tool-Rückgaben).
- Ab wann der alte Chat raus darf (Feature-Parität-Checkliste).
