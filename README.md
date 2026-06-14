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

### AI (pluggable providers)
- **Image descriptions** & **auto-tagging** in your chosen language.
- **Semantic search** via vector embeddings (pgvector, 768-dim).
- **Providers**: Google Gemini (cloud) · Ollama (local: llava, nomic-embed) — with fallback chain.

### People & Faces
- Face detection, clustering, and person management.
- **Merge / rename / delete** people, choose a **display avatar** (face crop).
- Person photo galleries.

### Albums
- **Manual** albums (hand-picked, re-orderable).
- **Smart** albums (rule-based: date, camera, person, media type, favorites, rating).
- **AI** albums (free-text prompt matched against descriptions).

### Other
- Timeline & justified grid gallery, lightbox, video player.
- Map view (GPS-tagged photos).
- Background job pipeline with logging.
- Encrypted backups.

---

## 🏗️ Architecture

| Layer      | Tech |
|------------|------|
| Backend    | FastAPI (Python 3.12), async SQLAlchemy, asyncpg |
| Database   | PostgreSQL 16 + **pgvector** |
| Queue      | Celery + Redis (worker + **beat** for folder watching) |
| Frontend   | React 18 + TypeScript + Tailwind + TanStack Query |
| Media tools| exiftool, ffmpeg, Pillow |
| Deploy     | Docker Compose on Proxmox LXC |

```
add source ──▶ scan_source_task ──▶ insert Photo + small thumb
                                       └─▶ process_photo_task (per photo)
                                              ├─ thumbnails (small/medium/large)
                                              ├─ AI description
                                              ├─ auto tags
                                              └─ text embedding
celery-beat ──▶ watch_sources (every 60s) ──▶ re-scan due sources
```

## 🚀 Run

```bash
cp .env.example .env   # set DB_PASSWORD, SECRET_KEY, PHOTOS_PATH, PORT
docker compose up -d --build
```

UI: `http://<host>:8090`  ·  API docs: `http://<host>:8090/api/docs`

Schema migrations are applied automatically on backend startup
(`CREATE TABLE IF NOT EXISTS` + idempotent `ADD COLUMN IF NOT EXISTS`).

## 🗺️ Roadmap

- [ ] Modern Immich/Google-Photos-style UI + mobile optimization
- [ ] Video face recognition (adaptive frame sampling)
- [ ] Additional local video/vision models (alternatives to moondream)
- [ ] Embedding provider selector (Gemini / Ollama / local)
- [ ] Map providers (geocoding) + richer geo features
- [ ] Relationships / family tree (toggleable)
- [ ] Auto-extract metadata settings for thumbnails
