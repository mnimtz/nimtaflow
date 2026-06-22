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
- **Vorschlags-Obergrenze raus** (v1.267): `suggest_faces` speicherte nur Gesichter mit `score < clustering_threshold` (0.5) → **starke Treffer (Sim ≥0.5, sogar Quasi-Duplikate mit Sim 1.0) wurden aktiv verworfen** und blieben für immer unzugeordnet — genau die „Top-Bilder, die nicht zugeordnet werden". Obergrenze entfernt; alles ≥ floor wird vorgeschlagen (1-Tap-Bestätigen, kein Auto-Merge). Diagnose-Lauf (numpy im Container) über 13.110 unzugeordnete: nur 90 haben Sim ≥0.5 (76 ≥0.6), **93,6 % liegen <0.40** = matchen objektiv niemanden (Profil/Kinder/Fremde/unbenannt) → Gesichts-Matching kann den Rest nicht retten.
- **Vorschlags-Qualität neu** (v1.266): `suggest_faces_task` von 1-NN (ein nächstes Exemplar gewinnt) auf **robusten Per-Personen-Score** umgestellt = Mittel der **Top-K** ähnlichsten Exemplare *pro Person*. Killt den Popularitäts-Bias (Lea hatte 219/623 Vorschläge, weil sie die meisten Exemplare hat) und 1-NN-Ausreißer. Distinktheit jetzt **zwischen Personen** (2.-bester Personen-Score) statt zwischen Einzelgesichtern. Mind. `suggest_min_exemplars` Exemplare nötig. Alle Schwellen settings-steuerbar (`face.suggest_min_score`=0.42, `face.suggest_margin`=0.06, `face.suggest_topk`=3, `face.suggest_min_exemplars`=3) → Tuning ohne Redeploy. Diagnose: alle alten Vorschläge lagen bei 0.40–0.45 = ArcFace-Rauschen (echte Treffer 0.5+ sind längst geclustert). Chunk auf 500 (OOM). **Nach Deploy: Task neu laufen lassen + Verteilung/Konzentration prüfen.**
- **Person-Detailseite Redesign** (v1.265): Profilkarte (größerer Avatar, Kontakt als klickbare Chips), **Unter-Tabs** Fotos/Gesichter/Beziehungen, **größere Gesichts-Crops**, **Beziehungen als SVG-Radial-Map** (Person mittig, Verbundene im Kreis, Linien nach Kategorie eingefärbt, Klick → Detailseite via `onOpenPerson`). Rein Frontend (`PersonDetailView` + neue `RelationshipsMap` in `frontend/src/pages/PeoplePage.tsx`), keine API-Änderung. Map nutzt `/relationships/person/:id`; Tab nur sichtbar wenn `features.relationships` an.

### ⏳ Offen
1. **Karte**: Orts-Liste mit Suche ausbauen (Teil da, `MapPage.tsx` ~134), **Seerouten-Layer** (Kreuzfahrten aus „Reisen"), **Eigenposition-Bug** („immer Grönland" — im Web KEIN Geolocation-Code gefunden → vmtl. iOS MapKit; beim User klären ob Web oder App).
2. **Mobile-Ansicht** grundlegend überarbeiten + Menüstruktur.
3. **Galerie**: „Erinnerungen"-Umschalter befüllen (Erinnerungen von Startseite hübsch zeigen).
4. **Reisen**: Bilder add/remove; Reiseroute als Karte (auf Schiffsroute optimiert).
5. **Highlights**: fertigstellen + testen, Personenwahl in Vorschlägen; **externe-Video-KI-Konzept** (Doku zuerst); Einstellungen erweitern.
6. **Externe-KI-Integration** (Alben/Smart-Alben → Videos/Clips/„Highlight der Woche").
7. **iOS-App**: ALLE Punkte spiegeln (`ios-app/`) — jetzt inkl. Person-Detailseite-Redesign.
8. **Push-Nachrichten-Konzept** + **iOS-Release-Readiness-Audit**.

### Älterer Backlog (kleinere offene Punkte)
- **Vision-Chat:** beim Foto-Chat die Top-Treffer-Thumbnails an Gemini mitschicken (nicht nur Text), damit das Modell die Bilder „sieht".
- **Video-Gesichts-Sweep (server-seitig):** Gesichter aus dem 1080p-Web-MP4 auf der SSD ziehen (insightface) statt 4K-Original — nightly/on-demand. (Teilweise vorhanden: `sweep_video_faces`/`detect_video_faces` auf der video-Queue.)
- **Karten-Eigenposition** („immer Grönland") — siehe Punkt 2 oben; vmtl. iOS-MapKit.

### Bekannte Daten-Realität
- ~13k „unbekannte Gesichter": die meisten haben **objektiv niedrige ArcFace-Ähnlichkeit** (Profil/Bewegung/Kinder) → auto-Clustering kann sie nicht sicher zuordnen ohne Falsch-Merges. Darum die Vorschläge-UI (Mensch bestätigt).
- Describe-Rückstau groß (~76k Bilder offen) — normaler Backlog, 1–2 Describe-Worker (~20–40 s/Bild).
- CPU-Queue (`process_photo`) drainet langsam (~30/min @ Concurrency 6); Metadaten via `backfill_metadata` (scan-Queue) entkoppelt.

_Letzter Stand-Commit: v1.267.0 (Vorschlags-Obergrenze raus). Versionen siehe git log._
