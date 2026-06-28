# Changelog

Versionen siehe `backend/app/version.py`. Deploy automatisch aus `main` (siehe `CLAUDE.md`).
Aktiver Roadmap-Stand: `ROADMAP.md`.

## v1.264.0 — Personen-Register (Tabs)
- PeoplePage in Tabs gegliedert: **Personen · Vorschläge · Unbekannte Gesichter · Verborgen** (mit Zählern).

## v1.263.0 — Vorschläge entschärft + Lightbox
- `suggest_faces`: Schwelle 0.32→**0.40** + **Distinktheits-Marge 0.04** → kein Popularitäts-Bias mehr (vorher 873× „Lea" falsch; jetzt nur distinkte Treffer, Ø-Ähnlichkeit ~0.42).
- **Lightbox**: Klick auf Vorschlag/Gesicht zeigt das **ganze Foto** groß (lädt auch bei leerem Video-Crop) inkl. ✓/✗.

## v1.262.0 — Kontaktdaten je Person
- `persons.email/phone/address` + Edit-Form + Anzeige (mailto:/tel:-Links).

## v1.260–1.261 — „Vorschläge bestätigen"-UI
- `faces.suggested_person_id/score` (plain Integer — **kein FK**, sonst bricht der Face-Mapper) + `suggest_faces`-Task (scan-Queue, gechunkt).
- API: `/people/faces/suggestions`, `confirm-suggestion`, `reject-suggestion`, `suggestions/confirm/{pid}`, `suggest`.

## v1.259.0 — Clustering-OOM-Fix
- Grow-Phase `X@E.T` in 1000er-Blöcken statt einer ~4-GB-Matrix → kein OOM-Kill mehr („Clustern bewirkt nichts" behoben).

## v1.258.0 — Metadaten-Stau beheben
- `backfill_metadata`-Task (scan-Queue, batched exiftool) zieht Datum+GPS+Geocoding direkt aus den Headern → Karte/Zeitleiste in Minuten statt nach dem `process_photo`-Backlog. Nächtlich + on-demand (`/photos/scan-metadata`).
- `process_photo` committet Datum/GPS/Kamera **vor** dem langsamen Thumbnail-Schritt.
- **Leitstand**: Indikator „X Fotos werden noch verarbeitet" + „GPS/Metadaten scannen"-Button.

## v1.256–1.257 — Video-Pipeline robust
- `transcode_video_task`: ffmpeg→`.part`→ffprobe-Validierung→atomares `os.replace` (keine no-moov-Torsos mehr); Cache-Datei wird revalidiert statt blind akzeptiert.
- `revalidate_transcodes`-Task + `/api/remote/video-broken` (Worker meldet kaputtes Web-MP4 → re-transcode).
- `generate_video_thumbnail`: Seek nie übers Clip-Ende (Sub-Sekunden-Clips) + Fallback auf Frame 0 → behebt falsch „defekt" markierte Videos.
- m3-video-Worker: degenerierte Ausgabe („!!!!") + nframes-Edge-Case sauber behandelt.
- m3-describe-Worker: leere Ollama-Antwort = transient (kein `ai_error` mehr).

## Betrieb (gelernt/dokumentiert)
- `useractivityd`/Universal-Clipboard-Bug räumte 161 GB auf dem Mac frei (Handoff aus).
- `defekte_bilder.txt`: 211 HEIC echt trunkiert (Quellkopien neu kopieren), 42 MOV/2 MP4 waren Fehlalarm (Seek-Bug).
