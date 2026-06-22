# PhotoFlow — Roadmap & aktueller Stand

> Quelle der Wahrheit für den Arbeitsstand (in git, reist mit dem Repo).
> NICHT auf projekt-gebundene Auto-Memory verlassen — die ist pro Ordner unterschiedlich.
> Bei neuem Stand: hier aktualisieren + committen.

## Große Feature-Kampagne (15 Punkte, blockweise, jeweils deployen)

### Entscheidungen des Users
- Clustering-Recall → **„Vorschläge bestätigen"-UI** (kein Threshold-Senken).
- Externe KI (Highlights/Video) → **erst Konzept-Dokument** (Provider-Vergleich Gemini/Veo/Runway, Kosten, Architektur, Einstellungen), dann bauen.
- iOS/Release → **erst Features bauen + iOS-Parität mitziehen**, Release-Readiness-Audit + Push-Konzept am Ende.
- Alle Punkte autonom abarbeiten; kritische ans Ende + Optionen erfragen.

### ✅ Erledigt (deployed)
- **Clustering-OOM-Fix** (v1.259): Grow-Phase `X@E.T` gechunkt (war ~4 GB → OOM-Kill „Clustern bewirkt nichts").
- **„Vorschläge bestätigen"** (v1.260–263): `faces.suggested_person_id/score` (plain Int, **kein FK!**) + `suggest_faces`-Task (scan-Queue, gechunkt) mit Schwelle `face.suggest_min_score`=0.40 **+ Distinktheits-Marge 0.04** (killt Popularitäts-Bias). API: `/people/faces/suggestions`, `confirm-suggestion`, `reject-suggestion`, `suggestions/confirm/{pid}`, `suggest`. PeoplePage-Sektion + **Lightbox** (Klick → ganzes Foto, lädt auch bei leerem Video-Crop) + ✓/✗.
- **Personen-Register/Tabs** (v1.264): Personen / Vorschläge / Unbekannte Gesichter / Verborgen (gaten die bestehenden Sektionen).
- **Kontaktdaten** (v1.262): `persons.email/phone/address` + Edit-Form + Anzeige (mailto/tel).
- **Leitstand GPS-Indikator + „GPS/Metadaten scannen"-Button** (v1.258) + `backfill_metadata`-Task (scan-Queue) + Struktur-Fix (process_photo committet Datum/GPS VOR Thumbnail).
- **Video-Pipeline** (v1.256–257): atomare/validierte Transcodes, `revalidate_transcodes`, `/video-broken`, `!!!!`-Degenerationsfilter, nframes-Edge-Case, Thumbnail-Sub-Sekunden-Seek-Fix.
- **m3-describe gehärtet**: leere Ollama-Antwort = transient (kein `ai_error`).

### ⏳ Offen
1. **Person-Detailseite Redesign**: größere Gesichter, Unter-Tabs (Gesichter/Fotos/**Beziehungen als Map**), modernes Layout, Kontaktdaten prominent. (`PersonDetailView` in `frontend/src/pages/PeoplePage.tsx` ~Z. 690+.)
2. **Karte**: Orts-Liste mit Suche ausbauen (Teil da, `MapPage.tsx` ~134), **Seerouten-Layer** (Kreuzfahrten aus „Reisen"), **Eigenposition-Bug** („immer Grönland" — im Web KEIN Geolocation-Code gefunden → vmtl. iOS MapKit; beim User klären ob Web oder App).
3. **Mobile-Ansicht** grundlegend überarbeiten + Menüstruktur.
4. **Galerie**: „Erinnerungen"-Umschalter befüllen (Erinnerungen von Startseite hübsch zeigen).
5. **Reisen**: Bilder add/remove; Reiseroute als Karte (auf Schiffsroute optimiert).
6. **Highlights**: fertigstellen + testen, Personenwahl in Vorschlägen; **externe-Video-KI-Konzept** (Doku zuerst); Einstellungen erweitern.
7. **Externe-KI-Integration** (Alben/Smart-Alben → Videos/Clips/„Highlight der Woche").
8. **iOS-App**: ALLE Punkte spiegeln (`ios-app/`).
9. **Push-Nachrichten-Konzept** + **iOS-Release-Readiness-Audit**.

### Bekannte Daten-Realität
- ~13k „unbekannte Gesichter": die meisten haben **objektiv niedrige ArcFace-Ähnlichkeit** (Profil/Bewegung/Kinder) → auto-Clustering kann sie nicht sicher zuordnen ohne Falsch-Merges. Darum die Vorschläge-UI (Mensch bestätigt).
- Describe-Rückstau groß (~76k Bilder offen) — normaler Backlog, 1–2 Describe-Worker (~20–40 s/Bild).
- CPU-Queue (`process_photo`) drainet langsam (~30/min @ Concurrency 6); Metadaten via `backfill_metadata` (scan-Queue) entkoppelt.

_Letzter Stand-Commit: v1.264.0 (+ m3-describe-Härtung). Versionen siehe git log._
