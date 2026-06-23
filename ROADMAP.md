# NimtaFlow — Roadmap & aktueller Stand

> Quelle der Wahrheit für den Arbeitsstand (in git, reist mit dem Repo).
> NICHT auf projekt-gebundene Auto-Memory verlassen — bei neuem Stand HIER aktualisieren + committen.
> Server-Zugang/Infra-Fallen stehen in `CLAUDE.md`.

**Stand: v1.315 (2026-06-23).** Security-Kapitel praktisch komplett (Rest: `/v1/chat`-ACL).
Nächster großer Block: **iOS-Parität → App Store**.

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

### 🟠 2 · Vor GitHub-Public (Achtung!)
- **`CLAUDE.md` steckt in der git-History** mit interner Infra (SSH-Hosts/IPs/Token-Pfade) → so NICHT public stellen, History vorher säubern.
- **Demo-Passwort** steht in `docs/appstore-listing.md` (bei public sichtbar).

### 🟡 3 · Feature-Politur
- **Highlights / externe Video-KI:** „Foto animieren" (Veo-3.1-MVP, default AUS) gebaut, aber **noch nie gegen die echte Veo-API getestet** (braucht Key + Test-Spend). Offen: **KI-Clip-Verschmelzung** (Slideshow + Veo-animierte Schlüsselbilder per ffmpeg stitchen, paid). Konzept: `docs/highlights-externe-video-ki-konzept.md`.
- **Lokaler M3-Video-Provider (LTX):** Worker-Skript `scripts/m3_ltx_worker.py` mit ffmpeg-Ken-Burns-Fallback steht; offen: **LTX-Modell-Install auf dem Mac + Job-Queue/Vorrat-Scheduler**.
- **Upload-Phase 3:** selbstverwaltete Quellen pro Nutzer.
- **Mobile-Web:** Bottom-Nav erneuert (4 Tabs + „Mehr"-Drawer); volle Per-Seiten-Responsiveness fehlt noch.

### 🟢 4 · Kleinkram / niedrige Prio
- **`/v1/chat` ACL** — Chat-Suche läuft noch über die ganze Bibliothek (letzter Security-Rest).
- **`albums.py` `datetime.utcnow()`** (naiv) — Rest vom app-weiten Zeitstempel-Fix (v1.285).
- **Vision-Chat:** Top-Treffer-Thumbnails an Gemini mitschicken (nicht nur Text).
- **Video-Gesichts-Sweep server-seitig** aus dem 1080p-MP4 statt 4K-Original (teilw. vorhanden: `sweep_video_faces`/`detect_video_faces`).

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
