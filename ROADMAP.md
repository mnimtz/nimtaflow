# NimtaFlow — Roadmap & aktueller Stand

> Quelle der Wahrheit für den Arbeitsstand (in git, reist mit dem Repo).
> NICHT auf projekt-gebundene Auto-Memory verlassen — bei neuem Stand HIER aktualisieren + committen.
> Server-Zugang/Infra-Fallen stehen in `CLAUDE.md`.

**Stand: v1.318 (2026-06-23).** Security komplett (inkl. `/v1/chat`-ACL). Kleinkram +
Feature-Politur abgearbeitet (außer M3-LTX + KI-Clip-Verschmelzung). GitHub-Public sauber.
**Einziger großer offener Block: iOS-Parität → App Store.**

---

## 🎯 Offene Punkte (priorisiert)

### 🔴 1 · iOS-App in den App Store (größtes Ziel)
- **iOS-Parität (`ios-app/`)** — alle Web-Features nachziehen (zuletzt offen: Person-Detail-Redesign, Karte-Routen/Orts-Panel, Reisen-Foto-add, Erinnerungen, Highlights-Fixes). Web-only per User-Entscheidung: Karte-Routen + Reisen-Foto-add (iOS-Datenmodell weicht ab).
- **iOS-Bugs (Code-Check):**
  - `GalleryView` Masonry/Justified-Layout (`GeometryReader` in `LazyVStack`, Höhe aus `UIScreen.width` ≠ geo) → Clipping/Pagination, braucht Geräte-Test
  - `APIError.decode` verschluckt `DecodingError` (nur Debug-Print)
  - **Karten-Eigenposition „immer Grönland"** (iOS-MapKit; Web hat keinen Geolocation-Code)
- **Store-Einreichung:** Screenshots/Metadaten (teils durch Website-Vorschau-Screenshots abgedeckt), finale Einreichung.
- **Push-Konzept + Release-Readiness-Audit** — Konzept-Doku da (`docs/push-und-release-audit-konzept.md`), Umsetzung offen.

### 🟢 1b · MCP-Server für NimtaFlow (Ph0–3 LIVE, v1.381–1.386)
- **Konzept-Doku:** `docs/mcp-server-konzept.md`. Code: `mcp-server/` (FastMCP, streamable-http, Container `photoflow-mcp-1`, Port 8091, Image `nimtaflow-mcp`).
- **Prinzip umgesetzt:** Metadaten = Motor (semantische Suche); Thumbnails nur Feinschliff; **temporärer Share-Link = Ergebnis**. Auth: Pro-User-JWT als Bearer durchgereicht → erbt ACL. Settings-Kategorie „MCP" (an/aus, `mcp.mode=read|read_write`, Share-TTL, Token erzeugen).
- **14 Tools live:** Lesen — `suche_medien`, `medien_detail` (mit Alter), `alben_liste`, `personen_liste`, `orte_liste`, `medien_im_umkreis` (GPS-Radius), `bibliothek_status`; Teilen — `teilen_link_erstellen` (foto/album/auswahl→Auto-Album); Schreiben (🔒 read_write) — `favorit_setzen`, `bewertung_setzen`, `album_erstellen`, `gesicht_zuordnen`, `gesicht_entfernen`, `vorschlaege_bestaetigen`.
- **Offen (Ph4):** async/kostenbewusst (Highlights/Video erzeugen), GPS-Einzel-Setzen, Postkarte. Multi-User: Token-Verwaltung/Rotation in Settings.

### 🟡 1c · Weitere Plattformen
- **macOS (Mac Catalyst) ✅ gebaut** (v1.3): `SUPPORTS_MACCATALYST=YES` + App-Sandbox-Entitlements + `LSApplicationCategoryType` + Mac-Catalyst-Distribution-Profil (per ASC-API erzeugt). Signiertes `.pkg` baut/läuft, in ASC hochgeladen (macOS-Plattform aktiv, MAC_OS-Version angelegt). **Offen:** Mac-Screenshots + finale Mac-Einreichung. Tooling: `ios-app/testflight-mac.sh` + `ExportOptions-mac-manual.plist`.
- **tvOS (Apple TV) — geplant, „Viewer".** NICHT nur Recompile (anders als Catalyst): Fokus-Navigation per Siri Remote, kein Touch/Kamera/Mikro → UI muss neu (fokusbasiert) gebaut werden. **Wiederverwendbar:** `APIClient`/`Models`/Auth/Netzwerk/Bild-Laden (~30–40 %). **Scope = Lean-back-Betrachter**, NICHT Feature-Parität: Galerie + Alben + Personen + **Highlights-Wiedergabe** + **Erinnerungs-Slideshow** (+ evtl. Karte/Reisen als Schauwert). Upload/Sprachmemos/Postkarten bewusst raus (passen nicht auf TV). Aufwand: eigenes tvOS-Target, fokusbasierte UI, tvOS-Sim-Test, eigene TV-Screenshots + eigene Review. Echtes Projekt, aber überschaubar bei Viewer-Beschränkung.

### 🟡 1d · Teilen / Sharing
- **Alles teilbar (erledigt, web + iOS):** Einzel-**Fotos & Videos** (Teilen-Button in der Lightbox), **Alben**, **Reisen**, **Highlights** (öffentliche Video-Seite mit Download) und **Postkarten** — alles per login-freiem, geheimem Link (`shares.py`, ShareTypes photo/album/trip/highlight/postcard; optional Passwort/Ablauf/Download; MCP-Tool `teilen_link_erstellen`).
- **Postkarte im Bild-Kontext (erledigt):** aus einem Foto eine teilbare Postkarte (Editor: Gruß + Nachricht, Themes warm/gold/dunkel/film/vintage, Schriftfarbe, Live-Vorschau, NimtaFlow-Logo) — Web-Share (Datei) **und** Link-Teilen. iOS mit Layout+Farbe.
- **🆕 GEPLANT — Video-Postkarte (kurze Clips ≤60 s, web-optimiert):** die Postkarte auf **Videos** erweitern. Ideen:
  - **Aufbau:** optionale **Intro-Titelkarte** (Gruß) → der **Clip (auf ≤60 s getrimmt)** → **Outro** (Nachricht + Logo). Alternativ dezente **Lower-Third**-Einblendung von Gruß/Name statt Vollbild-Karten. Render via ffmpeg (concat + drawtext + overlay), wie die Highlight-Pipeline.
  - **Themes wiederverwenden** (warm/gold/dunkel/film/vintage) für Rahmen/Schrift/Farbe; Schriftfarb-Option wie bei der Foto-Postkarte.
  - **Trim-UI in der Lightbox** (Video): Startpunkt + Länge wählen, hart auf **60 s** gedeckelt.
  - **Web-optimiert:** Ausgabe als kleines **H.264-MP4 (720/1080p, +faststart, gedeckelte Bitrate)** → spielt sofort auf der öffentlichen Share-Seite; **Poster-Bild**, autoplay-muted + Tap-to-unmute.
  - **Musik optional** (reuse Highlight-Musik/CC0/KI-Soundtrack) als Unterlegung/Überblendung.
  - **Auslieferung:** eigener ShareType-Variant `postcard`(video) bzw. `video_postcard`; öffentliche Seite rendert das Video mit Gruß; temporärer/ablaufender Link.
  - **Fallen:** Render kann dauern → async (pending→rendering→done wie Highlights) + Budget/Reaper; atomare Transcodes (`.part`→`os.replace`).
- **📌 Backlog — Motiv optimal in den Postkarten-Rahmen einpassen (Bilder UND Videos):** aktuell wird zugeschnitten (`cover`) oder verzerrt. Ziel: **nichts abgeschnitten, nichts verzerrt** — Seitenverhältnis erhalten und in den Rahmen einpassen (letterbox/pad mit themenpassendem Hintergrund, z. B. Blur-Fill wie beim Highlight-`_fill_graph`, oder smartes Crop, das Gesichter/Motiv nicht anschneidet). Gilt für Foto-Postkarte (Bild-Compositing) und Video-Postkarte (ffmpeg scale+pad statt crop/stretch).

### 🟡 1e · Ambient-KI-Assistent (Projekt gestartet — Phasen-Konzept steht)
**Konzept-Doku:** `docs/assistant-konzept.md` (Architektur „MCP nach innen", Settings, Ph0–5). **Ziel:** ersetzt den bisherigen KI-Chat-Menüpunkt, sobald stabil. **Settings-Bereich „Assistent":** Master an/aus, granulare Pro-Ansicht-Erlaubnisse (Galerie/Karte/Personen/Reisen/Highlights/Alben), Aktions-Stufe (nur lesen ↔ auch schreiben), **KI-Backend-Wahl lokal/Cloud**. **Phasen:** Ph0 Fundament (Overlay+Store, Galerie füllt sich) → Ph1 Karte+Galerie-Intents → Ph2 Aktionen (Highlight/Album/Teilen/Postkarte) → Ph3 Personen/Reisen/Wartung+Follow-ups → Ph4 iOS → Ph5 Settings + alten Chat entfernen.
**Kernidee:** Chat nicht als eigene Seite, sondern als **Assistent, der die aktuelle Ansicht steuert.** Kleines, immer sichtbares Symbol unten rechts (web + iOS) → öffnet ein **leicht transparentes, kleines Chat-Overlay**. Er kennt den **Kontext** (welche Ansicht, aktive Filter, gewählte Person) und **schiebt seine Antwort als Ergebnis-Set in genau diese Ansicht**.
- **Beispiel:** In der Galerie „Wann lernte Lea laufen?" → die **Galerie filtert sich** auf die Treffer (Chip „Ergebnisse für: …" + Clear). Man nutzt dann die volle Galerie (Lightbox, Auswahl, Album, Teilen, Details) *mit* den Antwort-Ergebnissen.
- **Technik liegt bereit:** `chat.py` macht schon Tool-Calls und liefert **`photo_ids`** → statt in die Chat-Blase zu rendern, in ein **gemeinsames „Ergebnis-Set"-State** schieben, das die Galerie/Karte/etc. anzeigt. Kontext (Ansicht/Filter/Person) an den Chat mitgeben.
- **Auch Aktionen im Kontext:** „mach daraus ein Album", „teile die drei", „starte ein Highlight" — auf dem gerade gezeigten Set.
- **Überall gleich:** Galerie (Foto-Filter), Karte (Pins filtern), Personen, Reisen; iOS mit demselben schwebenden Assistenten. Ergänzt „Frag das Foto" (pro Bild) als **app-weiten** Bruder.
- **UX:** klein/transparent, ggf. verschiebbar + Position merken, Tastenkürzel (z. B. ⌘/Long-Press).
- **Was der Assistent steuern könnte (Brainstorm):** Der Assistent bekommt „UI-Werkzeuge" (wie MCP-Tools, nach innen) und gibt strukturierte **View-Intents** zurück:
  - **Karte/Weltkugel:** „nur Bilder mit Lea" → nur GPS-Punkte mit Lea; „wo war ich 2022?" (Zoom auf Cluster); „nur Reisen/Italien", „als Heatmap", „Reiserouten"; „Fotos von diesem Punkt öffnen".
  - **Galerie:** filtern/sortieren/gruppieren („älteste zuerst", „nach Monat", „nur Videos/Favoriten"); auswählen+handeln („5 schönsten wählen", „als Favorit", „Album draus").
  - **Highlights:** „mach ein Highlight: Lea am Strand, ruhige Klaviermusik, 30 s" → Auftrag mit Person/Motiv/Musik/Länge, erscheint bei Highlights & rendert; „Jahresrückblick Anja 2023"; „animiere dieses Foto als Unterwasserwelt"; nachschärfen („Musik energischer/kürzer").
  - **Personen:** „alle mit Lea UND Anja", „wer am häufigsten mit mir", „Vorschläge für Lea bestätigen".
  - **Reisen:** „Reise 'Italien 2022' aus diesem Zeitraum anlegen", „Route zeigen", „Fotos hinzufügen".
  - **Alben/Teilen/Postkarte:** „Smart-Album 'Hunde'", „gezeigte ins Album Sommer", „die drei als Link teilen (Ablauf morgen)", „Postkarte mit Gruß X, Gold-Theme".
  - **Wartung:** „wie viele ohne Beschreibung?", „Gesichtserkennung starten", „Namen in Dateien schreiben", „verwaiste Duplikate aufräumen".
  - **Navigation/Hilfe:** „zu den Musik-Einstellungen", „erklär mir das Teilen".
  - **Verbindendes Konzept:** gemeinsames **„Ergebnis-Set + View-Intent"-State** — Assistent liefert strukturierte Kommandos, das Frontend führt sie in der aktuellen Ansicht aus → jede Ansicht ist „assistierbar", ohne dass der Chat sie kennen muss.

### ✅ 2 · GitHub-Public (erledigt 2026-06-23)
- **Zwei Repos:** `mnimtz/photoflow` (PRIVAT, Dev, volle bereinigte History) vs. `mnimtz/nimtaflow` (PUBLIC, kuratierter Snapshot). Public ist **sauber**: kein CLAUDE.md, keine internen IPs, kein Demo-PW, **0 Claude-Trailer**; Beschreibung/Website/Topics gesetzt; README mit Screenshots + Demo-Links; aktuell auf v1.315. Refresh-Prozedur: siehe Memory `keep-public-repo-current`.
- **Privates photoflow** ebenfalls bereinigt (CLAUDE.md aus History getilgt, IPs/PW/Claude-Trailer raus) — falls es je public wird, dann **vorher** GitHub-Token + Demo-PW rotieren (waren nur privat, also nie öffentlich abgeflossen).

### ✅ 3 · Feature-Politur (erledigt 2026-06-23, v1.316–1.318) — außer M3-LTX
- **Video-KI „Foto animieren" ✅ getestet & live** (v1.318-Test): fal.ai (Hailuo-02 i2v) end-to-end verifiziert (Highlight #6 → `/cache/highlights/clips/6.mp4`). Aktiviert mit Schutz-Budget **60s/Monat** (anpassbar). Veo-Pfad existiert ebenso; KI-Clip-Verschmelzung (Slideshow+Clips stitchen) weiterhin offen.
- **Upload-Phase 3 ✅** (v1.318): `owner_user_id` + Migration; `/api/my-sources` (Flag `allow_manage_sources`, realpath-Pfad-Validierung, Ownership); Profil-UI „Meine Quellen" (self-gating, DE/EN). Security verifiziert: außerhalb/Traversal/`/etc`→403, fremde Quelle→404, In-Scope→201.
- **Mobile-Web ✅** war bereits durchgängig responsiv (9 Seiten per Handy-Screenshots + Admin-Seiten per Code-Review geprüft — Bottom-Nav, `grid-cols-1/2`-Basis mit `sm:`/`lg:`-Scale-ups).
- **Offen nur:** **M3-LTX** (Modell-Install + Scheduler) + **KI-Clip-Verschmelzung** (paid, baut auf Veo/fal).

### ✅ 4 · Kleinkram (erledigt 2026-06-23, v1.316–1.317)
- **`/v1/chat` ACL ✅** (v1.316): Chat-Suche/Count über `photo_conditions(user)`; eingeschränkte Konten chatten nur über eigene Fotos (Schreib-Aktionen gesperrt), Pauschal-403 entfällt.
- **EXIF-NUL-Fix ✅** (v1.317): NUL/Steuerzeichen aus EXIF-Strings strippen — behob die „invalid byte sequence 0x00"-Fehlerflut (alte Canon-Kameras).
- **albums.py / Vision-Chat / Video-Gesichts-Sweep**: beim Prüfen bereits erledigt vorgefunden (aware `datetime.now(timezone.utc)`; `_image_parts`+`chat.vision`; Sweep liest 1080p-SSD-MP4).

### ✅ iOS-Rebrand-Check (2026-06-23)
- „NimtaFlow" an allen sichtbaren Stellen (Display-Name, Foto-Berechtigungstexte, Login, Settings, Dashboard-Logo); **LumaFlow = 0**; verbliebene „PhotoFlow" sind nur interne Bezeichner (Target/Scheme/Ordner) — bewusst.

---

## 🌐 Domain & Hosting
- **nimtaflow.com** (registriert 2026-06-23):
  - **login.nimtaflow.com** → App/Login (Server, CORS `*`). Privacy: `https://login.nimtaflow.com/privacy.html`.
  - **www.nimtaflow.com** → Marketing-Seite in `docs/website/` (Gold/Dark; Register Start/Funktionen/Vorschau/Download/Unterstützen + Datenschutz; DE/EN; PayPal `paypal.me/MNimtz`). Statisch (nginx) hinter Cloudflare-Tunnel; Deploy-Details in der lokalen `CLAUDE.md` (nicht im Repo).
    - **Vorschau-Register:** browser-gerahmte Screenshots (Galerie, Weltkugel, Startseite) aus dem Demo-Konto mit lizenzfreien Sample-Bildern, headless via Playwright erzeugt.
- **Demo-Konto** = Apple-Testaccount (Rolle user, auf den Demo-Ordner beschränkt), gefüllt mit lizenzfreien Natur-/Tierbildern. Zugangsdaten gehören in App Store Connect, NICHT ins Repo.

---

## ✅ Erledigt (verdichtet)

### Security (komplett, gegen Demo↔Admin verifiziert)
- **IDOR/Write-Guards** (v1.296–298): destruktive Foto-Mutationen (favorite/archive/rating/trash/**delete**/meta/reprocess/batch + v1) → `can_see_photo`; Personen-Management/Shares → Write-Guard/403; `/stats`, People, Relationships, Albums per `photo_conditions`/`visible_person_subquery` gescoped.
- **Pipeline-Guards** (v1.301): `require_pipeline` auf bibliotheksweiten POSTs; v1 preview/sprite mit `can_see_photo`; `/v1/upload` mit `user` + `allow_upload`.
- **FS-Browser & Sources admin-only** (v1.291), **Highlights per-User** (v1.290), **Erinnerungen-Leak** (v1.294).
- **Dashboard/People/Albums-Leak** (v1.313): eingeschränkte Konten sahen via Startseite/People/v1 die GANZE Bibliothek (Personen+Gesichter+counts, Album-Namen, Face-Tab-Zähler). Fix: durchgehend `visible_person_subquery(user)` + ACL-skalierte counts. **Personensicht ist damit korrekt ordner-abgeleitet** (gibst du Ordner X frei, sieht der Nutzer genau die Personen darunter).
- **v1-API + Bilder-Auth** (v1.314): `/v1/people`+`/v1/albums` gescoped. **Bilder-Bug:** absolute URLs aus `request.base_url` verlieren hinterm Proxy den Port → alle `<img>` tot. Jetzt **relative URLs** (same-origin, `pf_token`-Cookie; iOS strippt Host via `api.url(path)`). **Merke:** Thumbnail-Endpoint will `?access_token=`-Query bzw. `pf_token`-Cookie — kein Bearer bei `<img>`.
- **Offen:** `/v1/chat`-ACL (niedrige Prio).

### Verarbeitung / Worker
- **Stau behoben** (v1.315): Box = nur 6 Kerne, Load ~24. ~17,8k Fotos hingen ewig in `processing` (Task starb bei Deploy/Recreate nach den Thumbnails) → blähten den Zähler; Retry-Sweeps re-enqueuten genau diese → 46,7k cpu-Tasks Endlos-Churn. Fix: Reaper `reap_stuck_photos` (alle 10 min: processing+Thumb+>30min → done), `watch_sources` 60s→300s. Einmalig: 18k Karteileichen→done, Queue→0, 189 degenerierte Videos reaktiviert. **Load 24→7,7, echter Rückstand ~6,7k.**
- **Video-Beschreibungen** (Mac-Worker `m3-video`, Qwen3-VL): `mac_video_agent.py` — kosmetischer `TypeError`-Crash bei degenerierter „!!!!"-Ausgabe entfernt + **Sampling-Retry** (`temperature=0.6, repetition_penalty=1.15`) statt sofort `ai_error`.
- **Zeitstempel app-weit** (v1.285): `datetime.utcnow()` (naiv) → `app/core/timeutil.utcnow()` (aware) in allen 11 Models (−2h-Bug). **Rest: `albums.py`.**
- **Video-Pipeline** (v1.256–257, v1.287): atomare/validierte Transcodes, `.3gp`-Muxer-Fix (`-map 0:v:0? -map 0:a:0? -dn -sn`), `revalidate_transcodes`, `/video-broken`.
- **Clustering** (v1.259, v1.266–268): OOM-Fix (Grow-Phase gechunkt), Wurzelbug (asyncpg-Verbindung über synchrone numpy-Phase → `asyncio.to_thread` + Grow committet sofort), robuster Per-Personen-Top-K-Score.
- **Highlight-Render** (v1.283–284): ffmpeg via `asyncio.to_thread` (Connection-Starvation), Reaper für hängende Renders.

### Features
- **Rebrand → NimtaFlow** (v1.295): Web + iOS (`CFBundleDisplayName`) + Listing; GitHub-Repo `lumaflow`→`mnimtz/nimtaflow`; interne `photoflow`-IDs bewusst unverändert.
- **i18n komplett DE/EN** (v1.305): alle Seiten/Komponenten auf `useT`/`t()`, ~1000+ Keys, Browser-Erkennung + Umschalter, sandbox-tsc grün.
- **Gold-Branding** (v1.303): Web-Logo/Favicon + iOS-App-Icon.
- **Foto/Video-Upload** (v1.299–302): in `<home_root||folder_whitelist[0]||kürzeste Quelle||photos_path>/Upload/JJJJ/JJJJ-MM/`, deployment-agnostisch; iOS Auto (default AUS, „ab heute")/manuell.
- **Personen:** Vorschläge-bestätigen-UI + Tabs (v1.260–264), Kontaktdaten (v1.262), Detailseite-Redesign + Beziehungs-Radial-Map (v1.265), „Alle ablehnen" (v1.272).
- **Karte** (v1.270–271): Seerouten-Layer + durchblätterbares Orts-Panel.
- **Reisen** (v1.274): Fotos hinzufügen/entfernen + Routenkarte.
- **Highlights** (v1.275–278, v1.286): „Foto animieren"-MVP (Veo, opt-in), KI-Szenen-Presets, fal.ai-Provider, Album/Woche-Highlights + wöchentl. Auto-Lauf, Burst-Dedupe + Zeitverteilung, lokaler M3-Provider (Pull-Queue, LTX-Setup offen).
- **App-Store-Prep:** Demo-User + Privacy-Seite (v1.292), Listing-Texte (`docs/appstore-listing.md`), Mobile-Bottom-Nav (v1.288).
- **Lizenz/Recht** (v1.312): `LICENSE` (AGPL-3.0), Google-Fonts-Hotlink raus (DSGVO), AGPL-Quellcode-Link im Footer, `THIRD_PARTY_LICENSES.md` (NC-Modell-Disclaimer: buffalo_l/jina-clip-v2 nicht-kommerziell), Google-Map-Tiles (ToS) raus + OSM/CARTO-Attribution.

---

## Entscheidungen des Users
- Clustering-Recall → „Vorschläge bestätigen"-UI (kein Threshold-Senken).
- Externe Video-KI → erst Konzept-Doku, dann bauen.
- iOS/Release → erst Features + iOS-Parität, Release-Audit + Push am Ende.
- Group-3-iOS (Karte-Routen, Reisen-Foto-add) bleibt Web-only.
- NC-Modelle (buffalo_l/jina-clip-v2): Disclaimer reicht fürs private Self-Hosting; Swap auf permissive Engines nur bei kommerzieller Nutzung.

## Bekannte Daten-Realität (kein Bug)
- ~13k „unbekannte Gesichter": meist objektiv niedrige ArcFace-Ähnlichkeit (Profil/Bewegung/Kinder) → daher Vorschläge-UI.
- Describe-Rückstau groß (normaler Backlog, 1–2 Worker, ~20–40 s/Bild).
- Der Prod-Server hat nur 6 Kerne → Verarbeitung ist grundsätzlich langsam; Reaper hält den Zähler aber ehrlich.

_Versionen im Detail: `git log`._
