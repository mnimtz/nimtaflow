# 📸 PhotoFlow

Self-hosted photo & video management — a privacy-first alternative to Google Photos / Immich.
Runs entirely on your own hardware (LXC / Docker), keeps **originals read-only and untouched**,
and enriches your library with local or cloud AI.

> Status: active development. Deploys automatically from `main` to the LXC via a 5-minute git-poll + `docker compose build`.

---

## ✨ Features

### Library & Sources
- **Multiple watched folders** — add any number of source directories.
- **Automatic folder watching** — per-source re-scan interval (15 min … daily, or manual).
- **Deletion detection** — files removed from disk are flagged (`is_missing`), restored if they reappear.
- **Read-only originals** — sources are mounted `:ro`; PhotoFlow never modifies your files unless you explicitly opt in to EXIF/XMP writing.
- **Auto-pipeline** — adding a source immediately scans → thumbnails → AI description → tags → embedding.

### Metadata
- **Full EXIF storage** — camera, optics, exposure, GPS, IPTC/XMP, timezone, orientation, color space (~40 fields).
- **EXIF editing** — write title/caption/description/keywords/rating/GPS back into files (optional).
- **XMP sidecars** — write `.xmp` files (Dublin Core, IPTC) instead of touching originals (settings toggle).

### AI (pluggable providers, per medium)
- **Separate config** for **Bilder-AI** and **Video-AI** (different providers/models each).
- **Per-folder override** — force a specific provider (or `off`) for any source subtree.
- **Configurable prompts** for image & video descriptions (with sensible defaults).
- **Providers**: Google Gemini · Ollama (local) · **Integriert/Local** — running in-process, no Ollama needed:
  - **Florence-2-base** — ~0.5 GB VRAM, ~12 s/photo, English captions auto-translated to German (opus-mt).
  - **Qwen2.5-VL-3B** — native multilingual (German), loaded **4-bit (nf4)** so it fits an 8 GB card (~2.4 GB), ~23 s/photo.
- **GPU acceleration** — CUDA passthrough (RTX 2080 tested): the VLM runs in fp16/4-bit on the GPU; InsightFace face detection stays on CPU so the two don't fight for the 8 GB of VRAM. Input is capped to ~1280 px and the CUDA cache is freed per photo to avoid OOM/fragmentation.
- **Auto-tagging** (in the selected language) + **semantic search embeddings** (pgvector 768-dim; local e5 for the integrated provider).
- **AI write-back** for **any** provider: embed `dc:description`/IPTC + keywords into the file and/or a `.xmp` sidecar (mode: off / file / file+sidecar / sidecar). Full text, never truncated (XMP has no length limit); `-P` preserves the file timestamp so dates never become "today"; if a file has **no EXIF capture date**, the file date is written into `DateTimeOriginal` (+ DB) so it gets a stable date.
- **Re-use existing metadata on scan**: if a file already has a description (embedded XMP/IPTC **or** a `.xmp` sidecar), the scanner imports it and **skips the AI** (fast, saves GPU — e.g. after a re-import or DB recovery, the descriptions PhotoFlow wrote into the files are read back instead of recomputed). Force a fresh AI pass with `scan.force_reindex` (Settings → KI).
- **Tag prompt** (`Settings → KI`): leave empty → tags are derived from the caption (fast, no extra pass); set it → the VLM produces keywords in a dedicated pass (≈doubles GPU time). Output is sanitised (no JSON scaffold / instruction-echo / repetition loops).

### Videos
- **Formats**: mp4, mov, avi, mkv, m4v, webm, mts, m2ts, m2t, ts, vob, mpg, mpeg, wmv, flv, ogv, mod, 3gp — anything ffmpeg decodes.
- **Adaptive multi-frame AI** — for Qwen, frames are sampled **evenly across the whole clip** (`~1/45 s`, 4–16 frames) and fed as a video, so the description covers the entire video (not one frame). Shorter clips get fewer frames, long ones stay bounded.
- **Full-video hover preview** — an animated WebP "flipbook" sampled across the whole length (fast seeks, bounded even for hour-long videos), plus a sprite sheet for timeline scrubbing.
- **Instant playback**: the stream serves a cached, web-optimised **H.264 MP4 (+faststart)**; on first play it kicks off a background HW transcode (QSV/CUDA/VAAPI, software fallback) and serves the original meanwhile, so the next play starts immediately and non-streamable formats (MTS/VOB/…) become playable.
- **Face recognition in videos** (opt-in, Settings → Video-AI) — InsightFace runs on up to `video.max_frames` frames sampled across the whole clip, deduped by embedding so each person counts once; flows into the normal people clustering.
- **Dedicated `video` log** — start, length, resolution, preview yes/no, processing time, errors, and the AI description per video.

### People & Faces
- Face detection (InsightFace SCRFD + ArcFace, 512-dim embeddings) with auto-clustering into people. New faces grow existing people by **nearest-exemplar** match (not a blurred mean), so a person who varies a lot (e.g. a baby across ages) still gets matched. Clustering is **chunked** (no multi-GB similarity matrix) so it scales to 100k+ faces without OOM.
- **Confirm suggestions ("Ist das …?")** — borderline ArcFace matches that are too uncertain to auto-assign (but distinctive enough vs. other people) are surfaced as one-tap suggestions grouped per person, with ✓/✗ and "Alle bestätigen". Lets you place clear faces that auto-clustering can't (profile/motion/varying children) without risking false merges.
- **Register/Tabs**: Personen · Vorschläge · Unbekannte Gesichter · Verborgen.
- **Click a face → full photo** in a lightbox (verify even when a low-quality video-frame crop is unclear) with confirm/reject inline.
- **Contact details per person** — name, alias, birthday, e-mail, phone, address (mailto:/tel: links).
- **Merge / rename / hide / delete** people, **bulk** face assignment, **ignore** stray faces.
- Choose a **display avatar** per person (★ on any of their faces — also straight from a photo's detail view).
- **Schnell-Benenn-Modus** — full-screen, keyboard-driven naming of unnamed clusters (biggest first; Enter = name, Tab = skip, dissolve non-faces) to clear hundreds of clusters in minutes.
- **False-positive filter** (nightly + on-demand) re-checks face crops and removes hand/pattern detections — also from named persons.
- Person photos **sortable** (newest/oldest); face-crop cache kept warm so the People page never crops on-demand.
- Configurable engine (facenet / insightface), clustering algorithm + merge threshold; never mixes detectors.
- Person-based **smart albums** kept current automatically.

### Chat assistant (RAG / agent over the library)
- **`POST /api/chat`** — ask about the library in German. A tool-calling **agent**
  (Gemini) decides when to search, gets **fused** photo records (description +
  face-recognised names + tags + date/place) and reasons over them — so an
  anonymous "person in the blue shirt" plus recognised "Günter Nimtz" is
  understood as the same person. Answers are grounded in the retrieved photos and
  reference them by `#id`.
- **Vision** — the top hits' thumbnails are sent to Gemini so it can *see* the photos and answer visual details no description captured.
- **Actions** — the assistant can *act*, not just search: "erstelle ein Album mit allen Strandfotos von Lea 2022", "markiere die als Favorit" (album-create + favourite tools; safe & reversible, no delete).
- **Toggle `chat.provider`** (top of the chat): `gemini` (cloud, smart, only text leaves the house) or `local` (private RAG via the local Qwen — slower without a GPU on the host).
- Results open **in-app** (lightbox), media-type/year filters, and exact counts via a `zaehle_fotos` tool. Full chat UI tab.

### Relationships (optional, toggle in settings)
- Define connections between people (parent, sibling, partner, …).
- **Derive** siblings & grandparents automatically from parent links.
- Interactive **graph** + per-person view ("together with", shared photos).

### Trips / Reisen
- **AI trip planner** — describe a trip/cruise in plain words ("AIDA Mittelmeer ab Mallorca über Barcelona, Marseille, Rom"); Gemini builds a structured route (ports/cities with coordinates + dates from its geographic knowledge — no external geocoder).
- Saved as an **editable album**: photos in the date range are auto-assigned and can be **individually removed** if they don't fit.
- **Map route** — the real travelled path drawn from the photos' GPS (chronological line) + numbered, named waypoint markers from the AI route.
- **Auto-detected events** (time + place clusters) shown as suggestions.

### Albums
- **Manual** albums (hand-picked, re-orderable).
- **Smart** albums (rule-based: date, camera, person, media type, favorites, rating).
- **AI** albums (free-text prompt matched against descriptions).
- Albums are creatable from the **chat assistant** too.

### Library & Gallery
- **Watched folders** with per-source scan intervals + deletion detection.
- **Library verify/cleanup**: removes orphaned entries (deleted files *and* photos no longer under any watched source) incl. their thumbnails/previews/faces.
- Justified grid with **infinite scroll**, **sort** (newest/oldest/added/name), **page size**, multi-select + bulk actions, Library/Favorites/Archive/Trash views.
- Timeline with date scrubber, lightbox (swipe, full EXIF + AI tags + recognized people + inline metadata editing), animated video hover previews.
- **Search** matches the AI description **and the filename** (type e.g. `IMG_6801.JPG`).
- **"Original in voller Qualität öffnen"** button in the lightbox info panel — opens the untouched original photo/video (full resolution) in a new tab.

### Map & Globe
- **2D map** with **7 free no-key tile layers** (OSM, Esri satellite, CARTO dark/light/voyager, OpenTopoMap, Wikimedia); auto fit-to-photos; optional **Street View link** per photo.
- **3D globe** (react-globe.gl) of **all** photo locations (lightweight `/photos/map`, no 500-row cap); click a point to **fly the camera down** to it.
- **Place search ("Ort suchen")** over your *own* photo locations — city names come from **offline reverse-geocoding** (bundled city DB, no external request), so you can jump straight to any place you've been; city marker clustering.

### Users & Profiles
- **Login** (JWT + refresh; cookie mirror so `<img>` requests authenticate). Optional enforcement.
- **Admin user management** — create/edit/delete, roles, activate/deactivate, per-user **access control** (visible date range, person whitelist, folder white/blacklist, allow map/download/pipeline).
- **"Mein Profil"** (self-service) — change name, **email (= login)**, birthdate, **password** (verifies current), and upload a **profile avatar**.

### Backup & Restore
- **Full backup**: PostgreSQL dump (`pg_dump`) + **thumbnail cache** (`/cache`) + config (`/config`), each gzip'd.
- **Restore** the DB or extract config/thumbnails back; optional **rclone** offsite sync.
- **Verify** — non-destructively confirms a dump is complete & restorable (checks schema + photo rows).

### Teilen
- **Öffentliche Links** für Alben, einzelne Fotos/Videos und Reisen — login-freier Gäste-Zugriff über einen geheimen Token-Link (`/s/<token>`). Pro Link einstellbar: **Passwort**, **Ablaufdatum**, **Download der Originale**. Jede Anfrage prüft Token + Ablauf + Passwort + Zugehörigkeit (eine ID lässt sich nicht erraten/erweitern). Verwaltung unter **Einstellungen → Teilen** (inkl. öffentlicher Basis-URL für die Link-Erzeugung); widerrufbar mit einem Klick.

### Other
- Background job pipeline with **per-feature logs** (scanner / ai / faces / video / **remote** / system) shown live in the UI; a **dedicated scan worker** so re-indexing starts immediately instead of waiting behind the thumbnail queue.
- App **version shown in the sidebar** (matches the running Docker build).
- **Mobile**: responsive layout, bottom nav, redirect-to-login when unauthenticated.
- **iOS app** (SwiftUI, `ios-app/PhotoFlow/`) talking to the `/api/v1` endpoints. Tabs: **Galerie · Alben · Suche · Chat · Mehr** (Personen, Karte, Beziehungen, Einstellungen). Albums, the Gemini/local chat assistant (with tappable result thumbnails) and map points are served by dedicated `/api/v1/{albums,albums/{id}/photos,map,chat}` endpoints that return the same `PhotoV1` shape the gallery uses. Build/run via Xcode (no auto-deploy).

---

## 🏗️ Architecture

| Layer      | Tech |
|------------|------|
| Backend    | FastAPI (Python 3.12), async SQLAlchemy, asyncpg |
| Database   | PostgreSQL 16 + **pgvector** |
| Queue      | Celery + Redis — **two queues**: `cpu` (parallel) + `gpu` (single-slot) + **beat** |
| AI         | transformers (Florence-2 / Qwen2.5-VL 4-bit), InsightFace, sentence-transformers |
| Frontend   | React 18 + TypeScript + Tailwind + TanStack Query + react-photo-album / leaflet / globe.gl |
| Media tools| exiftool, ffmpeg, Pillow, libheif |
| Deploy     | Docker Compose on Proxmox LXC (CUDA passthrough) |

**Two-queue pipeline** — slow GPU work never starves fast work:

```
add source ─▶ scan_source ─▶ insert Photo + small thumb        ┐
                                                                │  cpu queue
celery-beat ─▶ watch_sources (60s) ─▶ re-scan due sources       │  worker-cpu (×4)
                                                                │
            process_photo ─▶ exif + thumbnails (s/m/l) ─────────┘
                    └─▶ ai_photo ─▶ description · tags · embedding · faces  ◀── gpu queue
                                                                                worker (×1, CUDA)
```

- **worker-cpu** (concurrency 4, no GPU): scanning, thumbnails, clustering, metadata.
- **worker** (concurrency 1, `runtime: nvidia`): the VLM + face detection — exactly one 3B model copy fits the 8 GB card.

## 🛰️ Remote GPU worker

Offload the heavy AI (description, tags, embedding, faces — photos **and** video
frames) from a weak host to a machine with a GPU. The worker is **generic and
storage-free**: it only receives a JPEG over HTTP and returns JSON, so it needs
no database, no file/NFS access, and runs in any environment.

**Same image, different mode** — there is no special worker image. On the GPU box:

```bash
# on the server (Settings → Remote-Worker): enable, generate a token,
# optionally pick a heavier "Remote-Modell" (e.g. Qwen) than the host can run.
# then, on the GPU machine (repo + Docker present):
PHOTOFLOW_SERVER=http://<server>:8090 PHOTOFLOW_REMOTE_TOKEN=<token> \
  docker compose -f docker-compose.remote-worker.yml up -d --build
```

- **Where to configure:** everything is set on the **server** (Settings →
  Remote-Worker): on/off, shared token, and the model the worker should use.
  The agent itself only needs the server URL + token.
- **Model independence:** `remote.model` lets the worker run a stronger model
  (Qwen on the GPU) even if the server host can only do Florence/CPU.
- **Smart hand-off:** when remote is enabled and a worker is alive, the local AI
  step yields its jobs to the worker; if the worker disappears, a fallback
  re-queues them locally so nothing stalls.
- **What stays local:** thumbnails and video **transcoding** (they need the file)
  — use Intel **Quick Sync** (`/dev/dri` passthrough) or NVENC on the host.

## 🚀 Run

```bash
cp .env.example .env   # set DB_PASSWORD, SECRET_KEY, PHOTOS_PATH, PORT
docker compose up -d --build
```

UI: `http://<host>:8090`  ·  API docs: `http://<host>:8090/api/docs`

Schema migrations are applied automatically on backend startup
(`CREATE TABLE IF NOT EXISTS` + idempotent `ADD COLUMN IF NOT EXISTS`).

## 🗺️ Roadmap

> Aktiver Arbeitsstand + offene Punkte der laufenden Feature-Kampagne: **[`ROADMAP.md`](ROADMAP.md)**.

- [x] **Face-suggestion confirm UI** ("Ist das …?") + People register/tabs + per-person contact details
- [x] **Robust face clustering** (chunked, no OOM) + leak-free transcode revalidation
- [x] **Metadata/GPS backfill** (decoupled scan-queue) + Leitstand processing indicator
- [x] Modern Immich/Google-Photos-style UI + mobile optimization
- [x] GPU acceleration (CUDA) for local AI
- [x] Relationships / family tree (toggleable) + searchable person picker
- [x] Full backup + restore (DB + thumbnails + config)
- [x] Self-service user profiles + avatars
- [x] **Remote GPU worker** — external machine over the network (Celery)
- [x] Video face recognition (adaptive frame sampling)
- [x] **Trips / Reisen** — AI route planner + editable albums + map route from photo GPS
- [x] **Offline reverse-geocoding** + map place search
- [x] **Chat actions** — create albums / favourite from the assistant
- [x] **Schnell-Benenn-Modus** for unnamed face clusters
- [x] **Per-photo on-demand reprocess** ("Neu verarbeiten")
- [ ] **Person timeline** with age (birthdates) — "Lea 2018–2026"
- [ ] **"Auf Karte zeigen"** from a photo; places **heatmap**
- [ ] **Quality score** (blur/exposure) → sort out bad shots
- [ ] **Duplicate-person merge assistant** (suggest similar clusters)
- [ ] **Near-duplicate / burst detection** (perceptual hash) → keep best
- [ ] **Shared albums / guest links** (per-user views)
- [ ] **Smarter thumbnails** — face-aware crop so heads aren't cut off
- [ ] **Mobile-first overhaul** — structure, menus, everything controllable from the phone
- [ ] Embedding provider selector (Gemini / Ollama / local)
