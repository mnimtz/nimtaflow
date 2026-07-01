# NimtaFlow — Vision-Roadmap (Next-Gen / KI)

> Ideen-Roadmap für die nächste Generation. Fokus: **modern, einzigartig, KI-getrieben,
> interaktiv** — und immer auf der vorhandenen Infrastruktur aufsetzend (jina-clip-Embeddings,
> Gesichtserkennung, Chat-Agent mit Tools, Highlight-/ffmpeg-Pipeline, MCP-Server, Share-Links).
> Operativer Status/Backlog steht weiter in `ROADMAP.md`. Erstellt 2026-07-01.

## Leitprinzipien (gelten für ALLES hier)
- **Privacy-first & self-hosted:** Jede KI-Funktion ist ohne Cloud nutzbar. Cloud ist optional, pro Feature.
- **Modellwahl 2×lokal + 2×Cloud** pro KI-Feature (bestehende Regel) — inkl. Lizenz-/Copyright-Check.
- **Web UND iOS** immer mitgedacht; gemeinsamer Backend-Service, dünne Clients.
- **Der Assistent ist der rote Faden:** Fast jedes Feature ist auch als natürlichsprachlicher
  Befehl an den Assistenten erreichbar (nach innen wie MCP-Tools), nicht nur als Button.
- **Kostenbewusst:** generative/Cloud-Aktionen laufen async mit Budget-Deckel + Reaper (wie Highlights).

---

## ⭐ Tier 1 — Flagship (die „Wow"-Features, interaktiv + KI)

### F1 · Sprich mit deinen Erinnerungen (Voice-Assistent)
Freihändige **Sprach-Konversation** mit dem Assistenten — v. a. auf iOS („zeig mir letzten Sommer
am See", gesprochen; Antwort wird **vorgelesen**). Multi-Turn, kontextbewusst.
- **Aufsetzen auf:** dem bestehenden Chat-Agenten (`chat.py`, Tool-Calling) — nur STT davor, TTS dahinter.
- **Modelle:** lokal **Whisper** (STT, MIT) + **Piper/Kokoro** (TTS, MIT/Apache); Cloud: OpenAI/Deepgram STT, ElevenLabs/OpenAI TTS.
- **Warum einzigartig:** eine self-hosted Foto-App, mit der man *redet* und die *zurückspricht* — sehr wenige können das.
- **Aufwand:** mittel (iOS Audio-Capture + Streaming-Endpunkt); Backend-Logik existiert.

### F2 · Erinnerungsfilm mit Erzählstimme
Aus „Erzähl mir von unserem Kroatien-Urlaub" wird ein **narriertes Video**: die KI schreibt ein
warmes, konkretes **Skript** (Orte/Personen/Zeit — der `rueckblick`-Tool liefert das Aggregat schon),
liest es per **TTS** ein und legt es über eine Ken-Burns-Slideshow mit **stimmungspassender Musik**.
- **Aufsetzen auf:** `highlights.py`/ffmpeg-Pipeline + `_recap` + Musik-Worker. Nur Narration + Audio-Mux neu.
- **Warum einzigartig:** kein „Slideshow mit Musik" von der Stange — ein echter, erzählter Kurzfilm deiner Erinnerung.
- **Aufwand:** mittel; alle Bausteine da (Skript aus LLM, TTS aus F1, Render aus Highlights).

### F3 · Lebende Smart-Alben (selbst-aktualisierend)
Natürlichsprachlich gespeicherte Suchen als **Alben, die mitwachsen**: „Lea lachend draußen",
„Essen aus Restaurants", „Sonnenuntergänge am Meer" — neue Fotos landen automatisch drin, sobald sie passen.
- **Aufsetzen auf:** Embeddings + Gesichts-/Datums-/Orts-Filter (`_structural_ids`, `search_photos`).
  Ein Smart-Album = gespeicherter Query (semantisch + Regeln), beim Öffnen/asynchron ausgewertet.
- **Assistent:** „mach daraus ein lebendes Album" auf dem aktuellen Ergebnis-Set.
- **Aufwand:** mittel (Query-Persistenz + Re-Eval-Job); Suche existiert bereits.

### F4 · KI-Bibliothekar (agentisches Aufräumen mit Freigabe)
„**Räum meine Bibliothek auf**": Der Assistent erstellt einen **Plan** (Duplikate/Serien, unbeschriftete
Fotos, unbestätigte Gesichter, falsche Aufnahmedaten, verwaiste Screenshots) und führt ihn **nach
expliziter Freigabe** Schritt für Schritt aus — ein autonomer, aber kontrollierter Librarian.
- **Aufsetzen auf:** vorhandene Tasks (Reprocess, Cluster, Gesichts-Sweep) + neue Analyse-Jobs (T2).
- **Warum einzigartig:** verwandelt „ich müsste mal aufräumen" in eine geführte, sichere Aktion.
- **Aufwand:** mittel–groß; Sicherheits-Muster (Vorschau + Bestätigungs-Turn) ist Pflicht.

---

## 🔷 Tier 2 — Starke Ergänzungen (großer Nutzen, klar machbar)

### T1 · Duplikate & Serien-Assistent mit Ästhetik-Score
Perceptual-Hash + Embedding-Clustering findet Duplikate/Bursts; ein **lokales Ästhetik-/Schärfe-Modell**
wählt automatisch „das Beste jeder Serie" (Augen offen, scharf, gut belichtet). Interaktive Review-UI.
Spart Platz auf der Cache-SSD (bekanntes Thema) und entrümpelt die Galerie.
- **Modelle:** lokal NIMA/CLIP-Aesthetic (permissiv); Blur-Detection via OpenCV.

### T2 · Screenshots & Belege automatisch aussortieren
Ein Klassifikator erkennt **Screenshots/Dokumente/Belege/Memes** und schiebt sie in eine eigene
„Kramschublade" — die Haupt-Galerie zeigt nur echte Fotos. (Deine Screenshots vom 27.06. sind genau der Fall.)
- **Aufsetzen auf:** Embeddings + einfacher Klassifikator/Heuristik; als Facet-Filter + Auto-Hide.

### T3 · Text in Bildern durchsuchbar (OCR)
**Lokales OCR** (PaddleOCR/Tesseract) über Fotos → Schilder, Whiteboards, Speisekarten, Dokumente
werden **volltext-durchsuchbar** und vom Assistenten nutzbar („das Foto mit der WLAN-Karte").
- **Warum stark:** massiver Recall-Gewinn, komplett lokal/privat.

### T4 · Auto-Event- & Reise-Erkennung mit KI-Titeln
Cluster nach **Zeit + Ort + Personen** → automatisch benannte Ereignisse: „Wochenende in Amsterdam ·
3 Personen · 120 Fotos". KI schlägt Titel/Cover vor; wird zu Reisen/Alben.
- **Aufsetzen auf:** GPS + Gesichter + Zeit; Reisen-Modell existiert schon.

### T5 · „Mehr wie dieses" — visuelle Ähnlichkeit
Aus jedem Foto per Embedding-Nachbarschaft **ähnliche Fotos** finden (Vibe/Komposition/Motiv).
„Finde Fotos in dieser Stimmung." Direkt in Lightbox + als Assistent-Tool.
- **Aufwand:** klein (Vektor-Nachbarsuche existiert).

### T6 · Alte Scans restaurieren (lokal, opt-in)
**Entrauschen / hochskalieren / Gesichter restaurieren** verblasster Familien-Scans
(Real-ESRGAN / GFPGAN, lokal, opt-in). „Restauriere dieses alte Foto." Nicht-destruktiv (Original bleibt).
- **Lizenz-Check** pro Modell; Ergebnis als neue Variante, nie Overwrite.

### T7 · Proaktiver Erinnerungs-Digest (Push + Widget)
Täglich KI-kuratiert: „Vor 3 Jahren heute…", „lange kein Foto von Oma", „entdecke wieder: Reise X".
Als **iOS-Widget / Lock-Screen-Foto des Tages** + optionaler Push (Push-Konzept liegt bereits vor).
- **Warum stark:** holt die App aktiv ins Leben, statt passiv zu warten.

---

## 🔹 Tier 3 — Ambitioniert / später

- **T8 · Objekt-/Personen-Entfernung (generatives Retuschieren):** Fotobomber/Touristen entfernen (Cloud opt-in, Budget-Deckel).
- **T9 · „Mein Jahr auf der Karte abspielen":** animierte Reise über Globus/Karte + Reise-Statistik (Länder, km). Interaktiv, hoher Schauwert (Karte/Weltkugel existieren).
- **T10 · Beziehungs- & Sozialgraph-Insights:** „wen fotografiere ich am häufigsten", „lange nicht gesehen", Ko-Vorkommen-Graph — interaktiv (Beziehungs-Radial-Map existiert).
- **T11 · Lebende Porträts / „X durch die Jahre":** per-Person Aging-Montage als Auto-Video; tasteful „living portrait" fürs Profil (animate-photo existiert).
- **T12 · Familien-Kollaboration:** geteilter Familien-Space, jede Person trägt bei, KI dedupliziert über Beitragende, gemeinsame Timeline — streng ACL-gescoped.

---

## ⚡ Quick Wins (bauen direkt auf dem eben Gelieferten auf)
Kleine, hochwirksame Schritte aus dem Multi-Agenten-Review (v1.431) — kurzfristig:
- **Ergebnis-Set durch Folgefragen tragen** (`context_ids`): „mach ein Album daraus", „nur die Videos
  davon", „die dritte favorisieren" — deterministisch auf dem zuletzt gezeigten Set statt Neu-Suche.
- **Chat-Aktionen ergänzen** (Endpunkte existieren schon): `bewertung_setzen`, `zu_album_hinzufuegen`
  (bestehendes Album), `vorschlaege_bestaetigen` (Gesichter), `medien_im_umkreis` (Ort/Radius),
  `teilen_link_erstellen` — der In-App-Assistent kann dann so viel wie der MCP-Server.
- **`gesamt_anzahl`-Deckel:** echte Gesamtzahl (2000er-Cap nur für die ID-Liste) separat melden,
  damit „alle Fotos von X" die WAHRE Zahl nennt (aktuell zeigt es max. 2000 statt z. B. 7742).
- **Zeitzonen** im Assistenten (`date.today()` → `Europe/Berlin`) für „heute/gestern" an Randzeiten.

---

## Modell- & Lizenz-Notizen (für die KI-Features hier)
- **STT:** Whisper (MIT) ✓ · **TTS:** Piper (MIT) / Kokoro ✓ · Cloud: OpenAI/ElevenLabs/Deepgram.
- **OCR:** Tesseract (Apache) / PaddleOCR (Apache) ✓.
- **Ästhetik:** CLIP-Aesthetic / NIMA — Lizenz je Gewicht prüfen.
- **Restauration:** Real-ESRGAN (BSD) / GFPGAN — Gewichts-Lizenz prüfen (teils NC → nur Self-Hosting-Disclaimer, wie buffalo_l/jina).
- **Generatives Retuschieren:** nur Cloud (fal/Replicate) mit Budget-Deckel; kein NC-Modell kommerziell.
- Grundsatz bleibt: **2 lokale + 2 Cloud** je Feature, Datenschutz & Copyright zuerst.

---

## Empfohlene Reihenfolge (wenn wenig Zeit)
1. **Quick Wins** (Assistent-Aktionen + context_ids) — billig, schließt den Review sauber ab.
2. **F2 Erinnerungsfilm mit Erzählstimme** + **F1 Voice** — teilen sich TTS/STT, maximaler „Wow".
3. **T3 OCR** + **T2 Screenshots aussortieren** — sofort spürbarer Alltagsnutzen.
4. **F3 Lebende Smart-Alben** + **T5 „mehr wie dieses"** — machen die Suche zum Erlebnis.
5. **F4 KI-Bibliothekar** — sobald die Analyse-Jobs (T1/T2) stehen, verbindet er alles.
