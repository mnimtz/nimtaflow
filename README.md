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
- **AI write-back** for **any** provider: embed `dc:description`/IPTC + keywords into the file and/or a `.xmp` sidecar (mode: off / file / file+sidecar / sidecar).

### People & Faces
- Face detection (InsightFace SCRFD + ArcFace, 512-dim embeddings) with auto-clustering into people.
- **Merge / rename / hide / delete** people, **bulk** face assignment, **ignore** stray faces.
- Choose a **display avatar** per person (★ on any of their faces).
- Configurable engine (facenet / insightface), clustering algorithm + merge threshold; never mixes detectors.
- Person-based **smart albums** kept current automatically.

### Relationships (optional, toggle in settings)
- Define connections between people (parent, sibling, partner, …).
- **Derive** siblings & grandparents automatically from parent links.
- Interactive **graph** + per-person view ("together with", shared photos).

### Albums
- **Manual** albums (hand-picked, re-orderable).
- **Smart** albums (rule-based: date, camera, person, media type, favorites, rating).
- **AI** albums (free-text prompt matched against descriptions).

### Library & Gallery
- **Watched folders** with per-source scan intervals + deletion detection.
- **Library verify/cleanup**: removes orphaned entries (deleted files *and* photos no longer under any watched source) incl. their thumbnails/previews/faces.
- Justified grid with **infinite scroll**, **sort** (newest/oldest/added/name), **page size**, multi-select + bulk actions, Library/Favorites/Archive/Trash views.
- Timeline with date scrubber, lightbox (swipe, full EXIF + AI tags + recognized people + inline metadata editing), animated video hover previews.

### Map & Globe
- **2D map** with **7 free no-key tile layers** (OSM, Esri satellite, CARTO dark/light/voyager, OpenTopoMap, Wikimedia); auto fit-to-photos; optional **Street View link** per photo.
- **3D globe** (react-globe.gl) of all photo locations; click a point to **fly the camera down** to it.

### Users & Profiles
- **Login** (JWT + refresh; cookie mirror so `<img>` requests authenticate). Optional enforcement.
- **Admin user management** — create/edit/delete, roles, activate/deactivate, per-user **access control** (visible date range, person whitelist, folder white/blacklist, allow map/download/pipeline).
- **"Mein Profil"** (self-service) — change name, **email (= login)**, birthdate, **password** (verifies current), and upload a **profile avatar**.

### Backup & Restore
- **Full backup**: PostgreSQL dump (`pg_dump`) + **thumbnail cache** (`/cache`) + config (`/config`), each gzip'd.
- **Restore** the DB or extract config/thumbnails back; optional **rclone** offsite sync.
- **Verify** — non-destructively confirms a dump is complete & restorable (checks schema + photo rows).

### Other
- Background job pipeline with **per-feature logs** (scanner / ai / faces / video / system) shown live in the UI.
- App **version shown in the sidebar** (matches the running Docker build).
- **Mobile**: responsive layout, bottom nav, redirect-to-login when unauthenticated.
- **iOS app** (SwiftUI) talking to the `/api/v1` endpoints.

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

- [x] Modern Immich/Google-Photos-style UI + mobile optimization
- [x] GPU acceleration (CUDA) for local AI
- [x] Relationships / family tree (toggleable)
- [x] Full backup + restore (DB + thumbnails + config)
- [x] Self-service user profiles + avatars
- [ ] **Richer relationship types** (husband/wife/son/daughter/uncle/colleague…) with searchable picker + typed family/company trees
- [ ] **Remote GPU worker** — attach an external machine to speed up initial processing (Celery worker over the network)
- [ ] **Smarter thumbnails** — face-aware crop so heads aren't cut off
- [ ] **Pipeline dashboard** — error queue with one-click reprocess
- [ ] Video face recognition (adaptive frame sampling)
- [ ] Embedding provider selector (Gemini / Ollama / local)
