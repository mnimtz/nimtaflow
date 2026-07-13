from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware

from app.core.database import init_db, _engine
from app.version import __version__
from app.api.routes import auth, photos, people, sources, settings_api, jobs, my_sources
from app.api.routes import fs, ai_api, logs, backup, albums
from app.api.v1 import router as v1_router


# Idempotent schema migrations applied on every startup.
# create_all() only creates *missing tables* — it never ALTERs an existing table,
# so any column added to a model after its table first existed must be added here.
# Each entry must be a single SQL statement (DO $$..$$ blocks count as one).
_COLUMN_MIGRATIONS = [
    # ── shares: highlight sharing ─────────────────────────────────────────────
    "ALTER TABLE shares ADD COLUMN IF NOT EXISTS highlight_id INTEGER",
    "ALTER TABLE shares ADD COLUMN IF NOT EXISTS params JSONB",
    "ALTER TABLE shares ADD COLUMN IF NOT EXISTS allow_upload BOOLEAN DEFAULT false",
    "ALTER TABLE photos ADD COLUMN IF NOT EXISTS voice_note_path VARCHAR(512)",
    "ALTER TABLE photos ADD COLUMN IF NOT EXISTS faces_written_at TIMESTAMPTZ",
    "ALTER TABLE photos ADD COLUMN IF NOT EXISTS blur_data TEXT",
    # ── photos: full v2 metadata set ──────────────────────────────────────────
    """ALTER TABLE photos
        ADD COLUMN IF NOT EXISTS taken_at_original    VARCHAR(32),
        ADD COLUMN IF NOT EXISTS timezone_offset      VARCHAR(8),
        ADD COLUMN IF NOT EXISTS orientation          INTEGER,
        ADD COLUMN IF NOT EXISTS color_space          VARCHAR(32),
        ADD COLUMN IF NOT EXISTS camera_serial        VARCHAR(128),
        ADD COLUMN IF NOT EXISTS lens_make            VARCHAR(128),
        ADD COLUMN IF NOT EXISTS focal_length_35mm    INTEGER,
        ADD COLUMN IF NOT EXISTS exposure_time        FLOAT,
        ADD COLUMN IF NOT EXISTS exposure_mode        VARCHAR(64),
        ADD COLUMN IF NOT EXISTS metering_mode        INTEGER,
        ADD COLUMN IF NOT EXISTS white_balance        INTEGER,
        ADD COLUMN IF NOT EXISTS flash                INTEGER,
        ADD COLUMN IF NOT EXISTS software             VARCHAR(256),
        ADD COLUMN IF NOT EXISTS gps_accuracy         FLOAT,
        ADD COLUMN IF NOT EXISTS country_code         VARCHAR(4),
        ADD COLUMN IF NOT EXISTS artist               VARCHAR(256),
        ADD COLUMN IF NOT EXISTS copyright            VARCHAR(512),
        ADD COLUMN IF NOT EXISTS title                VARCHAR(512),
        ADD COLUMN IF NOT EXISTS caption              TEXT,
        ADD COLUMN IF NOT EXISTS keywords             TEXT,
        ADD COLUMN IF NOT EXISTS xmp_sidecar_written  BOOLEAN NOT NULL DEFAULT FALSE,
        ADD COLUMN IF NOT EXISTS xmp_sidecar_path     VARCHAR(2048),
        ADD COLUMN IF NOT EXISTS xmp_last_written_at  TIMESTAMPTZ,
        ADD COLUMN IF NOT EXISTS description_model    VARCHAR(128),
        ADD COLUMN IF NOT EXISTS video_fps            FLOAT,
        ADD COLUMN IF NOT EXISTS video_bitrate        INTEGER,
        ADD COLUMN IF NOT EXISTS user_description     TEXT""",
    # ── photos: folder-watch / deletion detection ─────────────────────────────
    "ALTER TABLE photos ADD COLUMN IF NOT EXISTS is_missing BOOLEAN NOT NULL DEFAULT FALSE",
    "ALTER TABLE photos ADD COLUMN IF NOT EXISTS missing_at TIMESTAMPTZ",
    "ALTER TABLE photos ADD COLUMN IF NOT EXISTS video_preview_path VARCHAR(512)",
    "ALTER TABLE photos ADD COLUMN IF NOT EXISTS ai_error BOOLEAN NOT NULL DEFAULT FALSE",
    # ── photos: harter Failure-Counter für Transcode ─────────────────────────
    # Nach 3 fehlgeschlagenen Transcode-Versuchen ignoriert der Sweep die
    # Photo-ID — sonst queued er dieselben kaputten Files bei jedem Beat-Lauf
    # neu und die video-Queue wächst ins Endlose.
    "ALTER TABLE photos ADD COLUMN IF NOT EXISTS video_transcode_failures INTEGER NOT NULL DEFAULT 0",
    # Ehrliche Progress-Anzeige im Leitstand: getrennte Timestamps je Rendition,
    # damit „fertig transcodiert" nicht mehr die alten 10-bit-Files aus vor dem
    # v1.525-Fix mitzählt. Wird beim transcode_result gesetzt.
    "ALTER TABLE photos ADD COLUMN IF NOT EXISTS web_mp4_720_at  TIMESTAMPTZ",
    "ALTER TABLE photos ADD COLUMN IF NOT EXISTS web_mp4_1080_at TIMESTAMPTZ",
    # ── photos: face-aware crop, remote-worker lease, >2GB file sizes ─────────
    "ALTER TABLE photos ADD COLUMN IF NOT EXISTS focus_x DOUBLE PRECISION",
    "ALTER TABLE photos ADD COLUMN IF NOT EXISTS focus_y DOUBLE PRECISION",
    "ALTER TABLE photos ADD COLUMN IF NOT EXISTS ai_claimed_at TIMESTAMPTZ",
    "ALTER TABLE photos ADD COLUMN IF NOT EXISTS imported_person_names TEXT",
    "ALTER TABLE photos ADD COLUMN IF NOT EXISTS faces_scanned BOOLEAN NOT NULL DEFAULT FALSE",
    "ALTER TABLE photos ADD COLUMN IF NOT EXISTS ai_attempts INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE photos ADD COLUMN IF NOT EXISTS thumb_attempts INTEGER NOT NULL DEFAULT 0",
    # jina-clip-v2: description-text vector (image vector reuses the existing `embedding` col)
    "ALTER TABLE photos ADD COLUMN IF NOT EXISTS embedding_text vector(768)",
    # TYPE changes are guarded so they don't rewrite the table on every startup.
    """DO $$ BEGIN
        IF (SELECT data_type FROM information_schema.columns
            WHERE table_name='photos' AND column_name='file_size') <> 'bigint' THEN
          ALTER TABLE photos ALTER COLUMN file_size TYPE BIGINT;
        END IF;
    END $$""",
    # ── photos: trash timestamp (drives retention auto-purge) ─────────────────
    "ALTER TABLE photos ADD COLUMN IF NOT EXISTS trashed_at TIMESTAMPTZ",
    # ── users: self-service profile + "this is me" person link ────────────────
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS birthdate VARCHAR(32)",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar_path VARCHAR(512)",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS person_id INTEGER",
    # ── photo_sources: Upload-Phase 3 — per-user owned sources ────────────────
    "ALTER TABLE photo_sources ADD COLUMN IF NOT EXISTS owner_user_id INTEGER",
    # ── photos: folder hidden from display (face recognition still runs) ───────
    "ALTER TABLE photos ADD COLUMN IF NOT EXISTS is_hidden BOOLEAN NOT NULL DEFAULT FALSE",
    # ── photos: updated_at + trigger (drives iOS incremental sync) ────────────
    "ALTER TABLE photos ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW()",
    "CREATE OR REPLACE FUNCTION pf_touch_updated_at() RETURNS trigger AS $$ BEGIN NEW.updated_at = NOW(); RETURN NEW; END; $$ LANGUAGE plpgsql",
    "DROP TRIGGER IF EXISTS pf_photos_updated_at ON photos",
    "CREATE TRIGGER pf_photos_updated_at BEFORE UPDATE ON photos FOR EACH ROW EXECUTE FUNCTION pf_touch_updated_at()",
    # ── relationships: rel_type is now a free string (was a native enum) ──────
    """DO $$ BEGIN
        IF (SELECT data_type FROM information_schema.columns
            WHERE table_name='person_relationships' AND column_name='rel_type') <> 'character varying' THEN
          ALTER TABLE person_relationships ALTER COLUMN rel_type TYPE VARCHAR(32) USING rel_type::text;
        END IF;
    END $$""",
    # ── photo_sources: watching ───────────────────────────────────────────────
    "ALTER TABLE photo_sources ADD COLUMN IF NOT EXISTS scan_interval_minutes INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE photo_sources ADD COLUMN IF NOT EXISTS detect_deletions BOOLEAN NOT NULL DEFAULT TRUE",
    "ALTER TABLE photo_sources ADD COLUMN IF NOT EXISTS ai_provider VARCHAR(32)",
    # ── albums: smart/ai types ────────────────────────────────────────────────
    "DO $$ BEGIN CREATE TYPE albumtype AS ENUM ('manual','smart','ai'); EXCEPTION WHEN duplicate_object THEN NULL; END $$",
    """ALTER TABLE albums
        ADD COLUMN IF NOT EXISTS album_type        albumtype NOT NULL DEFAULT 'manual',
        ADD COLUMN IF NOT EXISTS smart_criteria    JSONB,
        ADD COLUMN IF NOT EXISTS ai_prompt         TEXT,
        ADD COLUMN IF NOT EXISTS ai_last_evaluated TIMESTAMPTZ,
        ADD COLUMN IF NOT EXISTS updated_at        TIMESTAMPTZ DEFAULT NOW()""",
    "ALTER TABLE album_photos ADD COLUMN IF NOT EXISTS ai_score FLOAT",
    # ── persons: alias / hide ─────────────────────────────────────────────────
    "ALTER TABLE persons ADD COLUMN IF NOT EXISTS alias VARCHAR(256)",
    "ALTER TABLE persons ADD COLUMN IF NOT EXISTS is_hidden BOOLEAN NOT NULL DEFAULT FALSE",
    # ── faces: ignore/hide ────────────────────────────────────────────────────
    "ALTER TABLE faces ADD COLUMN IF NOT EXISTS is_ignored BOOLEAN NOT NULL DEFAULT FALSE",
    "ALTER TABLE faces ADD COLUMN IF NOT EXISTS frame_time DOUBLE PRECISION",
    # ── faces: ArcFace "suggested match" (borderline sim a human confirms) ─────
    "ALTER TABLE faces ADD COLUMN IF NOT EXISTS suggested_person_id INTEGER",
    "ALTER TABLE faces ADD COLUMN IF NOT EXISTS suggested_score DOUBLE PRECISION",
    # ── persons: optional contact details ─────────────────────────────────────
    "ALTER TABLE persons ADD COLUMN IF NOT EXISTS email   VARCHAR(256)",
    "ALTER TABLE persons ADD COLUMN IF NOT EXISTS phone   VARCHAR(64)",
    "ALTER TABLE persons ADD COLUMN IF NOT EXISTS address VARCHAR(512)",
    # ── pg_trgm für schnelle ILIKE '%..%' Suche auf description + filename ────
    # Ohne trgm-GIN läuft jede Freitextsuche im Backend als Sequential Scan über
    # die volle Photos-Tabelle. Mit dem GIN-Index klappt es in ms.
    "CREATE EXTENSION IF NOT EXISTS pg_trgm",
    "CREATE INDEX IF NOT EXISTS ix_photos_description_trgm "
    "ON photos USING gin (description gin_trgm_ops) "
    "WHERE description IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS ix_photos_filename_trgm "
    "ON photos USING gin (filename gin_trgm_ops)",
    # ── Partial-Indexes für die Kern-Query der Bibliotheks-Timeline ───────────
    # Die Standard-Galerie-Query (view=library, sort=newest) hatte keinen
    # passenden Index. Postgres scannte über 140k Rows und filterte.
    "CREATE INDEX IF NOT EXISTS ix_photos_lib_timeline "
    "ON photos (taken_at DESC NULLS LAST, id DESC) "
    "WHERE is_trashed=false AND is_archived=false AND is_missing=false AND thumb_small IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS ix_photos_favorites_timeline "
    "ON photos (taken_at DESC NULLS LAST, id DESC) "
    "WHERE is_favorite=true AND is_trashed=false AND thumb_small IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS ix_photos_trash_timeline "
    "ON photos (trashed_at DESC NULLS LAST, id DESC) "
    "WHERE is_trashed=true",
    # ── users: defensive (in case the table predates these columns) ───────────
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS access_config JSONB",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_pro BOOLEAN NOT NULL DEFAULT FALSE",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS pro_source VARCHAR(32)",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS totp_secret VARCHAR(64)",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS totp_enabled BOOLEAN NOT NULL DEFAULT FALSE",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_login TIMESTAMPTZ",
    # v1.549: strukturierte Beschreibung (JSONB) für präzise Chat-Filter
    "ALTER TABLE photos ADD COLUMN IF NOT EXISTS structured_desc JSONB",
    "CREATE INDEX IF NOT EXISTS ix_photos_structured_desc_gin ON photos USING gin (structured_desc jsonb_path_ops)",
    # v1.561: Spezielle Medien (360° + Drohnen). is_360/is_drone als indexierte
    # Booleans für schnelle Filter, plus JSONB für Extra-Metadaten (Höhe, FOV, etc.)
    "ALTER TABLE photos ADD COLUMN IF NOT EXISTS is_360 BOOLEAN NOT NULL DEFAULT FALSE",
    "ALTER TABLE photos ADD COLUMN IF NOT EXISTS is_drone BOOLEAN NOT NULL DEFAULT FALSE",
    "ALTER TABLE photos ADD COLUMN IF NOT EXISTS drone_metadata JSONB",
    "ALTER TABLE photos ADD COLUMN IF NOT EXISTS pano_metadata JSONB",
    "CREATE INDEX IF NOT EXISTS ix_photos_is_360 ON photos (is_360) WHERE is_360 = true",
    "CREATE INDEX IF NOT EXISTS ix_photos_is_drone ON photos (is_drone) WHERE is_drone = true",
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Refuse to run with the built-in dev signing key (would let anyone forge
    # tokens). Set SECRET_KEY in .env.
    from app.core.config import get_settings as _gs
    if _gs().secret_key == "dev-secret-key-change-in-production":
        raise RuntimeError("SECRET_KEY is unset/default — set a strong SECRET_KEY in .env before running.")
    init_db()
    from app.core.database import Base, _engine
    import app.models  # noqa
    from sqlalchemy import text
    # Startup-Safety: einen früheren Backend-Prozess der zwischen Deploy-Recreate abriss
    # kann "idle in transaction" hinterlassen (langer SELECT offen). Der hält einen
    # AccessShareLock auf photos → jede ALTER TABLE (unten) wartet ewig und die App
    # kommt nie hoch (nginx = 502). Vor der Migration alle idle-in-tx > 30 s killen,
    # die NICHT unser eigener Prozess sind. Idempotent, nie fatal.
    try:
        async with _engine.begin() as conn:
            await conn.execute(text(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname=current_database() AND pid <> pg_backend_pid() "
                "  AND state = 'idle in transaction' "
                "  AND xact_start < now() - interval '30 seconds'"
            ))
    except Exception:
        pass
    async with _engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
    # Lightweight column migrations (create_all never ALTERs existing tables).
    # Each in its OWN transaction + non-fatal: a single failing/edge-case ALTER must
    # never abort the whole batch and crash startup (all statements are IF NOT EXISTS
    # / idempotent, so skipping a failed one is safe). Previously one shared txn meant
    # any single failure rolled back ALL migrations and propagated out of lifespan.
    import logging as _logging
    for stmt in _COLUMN_MIGRATIONS:
        try:
            async with _engine.begin() as conn:
                # lock_timeout=15s: wenn eine Migration ihren Lock nicht bekommt (weil
                # ein anderer Prozess die Tabelle sperrt) → sauber failen und nächste
                # probieren, statt Startup blockieren. Bei "IF NOT EXISTS" ist das
                # unkritisch: der Skip wird beim nächsten Start automatisch nachgeholt.
                await conn.execute(text("SET LOCAL lock_timeout = '15s'"))
                await conn.execute(text(stmt))
        except Exception:
            _logging.getLogger("photoflow").warning("migration skipped: %s", stmt[:80])

    # Enum value additions — a new column doesn't extend an existing PG enum type.
    # Each in its own transaction + non-fatal so one failure never blocks startup.
    for _stmt in ("ALTER TYPE sharetype ADD VALUE IF NOT EXISTS 'highlight'",
                  "ALTER TYPE sharetype ADD VALUE IF NOT EXISTS 'postcard'"):
        try:
            async with _engine.begin() as conn:
                await conn.execute(text(_stmt))
        except Exception:
            pass

    # Seed an initial admin if there are no users yet (idempotent, non-fatal).
    try:
        from app.core.database import get_db
        from app.models.user import User, UserRole
        from app.core.security import hash_password
        from sqlalchemy import select, func as _func
        import os
        async for db in get_db():
            count = await db.scalar(select(_func.count()).select_from(User))
            # Seed an initial admin only on an empty DB, and only if credentials
            # are provided via env (no hardcoded password in the repo).
            seed_email = os.getenv("INITIAL_ADMIN_EMAIL", "admin@photoflow.local")
            seed_pw = os.getenv("INITIAL_ADMIN_PASSWORD", "")
            if not count and seed_pw:
                db.add(User(
                    email=seed_email, name="Admin",
                    hashed_password=hash_password(seed_pw), role=UserRole.admin,
                ))
                await db.commit()
            elif not count:
                import logging
                logging.getLogger("photoflow").warning(
                    "No users and INITIAL_ADMIN_PASSWORD unset — create the first admin manually.")
            break
    except Exception as e:
        import logging
        logging.getLogger("photoflow").error(f"Admin-Seeding übersprungen: {e}")
    # Auto-fetch FireTV APK if FIRETV_APK_URL is set and file is missing (non-fatal).
    import asyncio as _asyncio
    from app.api.routes.software import auto_fetch_if_missing as _auto_apk
    _asyncio.ensure_future(_auto_apk())

    yield
    if _engine:
        await _engine.dispose()


app = FastAPI(
    title="PhotoFlow",
    version=__version__,
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*", "Range"],
    expose_headers=["Content-Range", "Accept-Ranges", "Content-Length", "X-PhotoFlow-Version"],
)

# ── Auth (always open) + user management (admin-only, self-guarded) ──────────
from app.api.routes import users as users_routes
from app.core.auth_guard import enforce_auth, block_restricted_writes
app.include_router(auth.router, prefix="/api")
app.include_router(users_routes.router, prefix="/api")

# ── Device Authorization (TV/FireTV/tvOS QR login — no auth required) ────────
from app.api.routes import device_auth as device_auth_routes
app.include_router(device_auth_routes.router, prefix="/api")

# ── Remote worker API (own shared-token auth, NOT user-guarded) ──────────────
from app.api.routes import remote as remote_routes
app.include_router(remote_routes.router, prefix="/api")

# ── Web data routes — gated by enforce_auth (no-op until auth.enforce=true) ──
_guard = [Depends(enforce_auth)]
# Management routers: same auth + a restricted (demo) account may read but not mutate.
_guard_ro = [Depends(enforce_auth), Depends(block_restricted_writes)]
app.include_router(photos.router, prefix="/api", dependencies=_guard)
app.include_router(people.router, prefix="/api", dependencies=_guard_ro)
app.include_router(sources.router, prefix="/api", dependencies=_guard)
# Per-user self-managed sources (Upload-Phase 3) — auth only; the router itself
# enforces the allow_manage_sources flag + path-scope, so NOT _guard_ro (restricted
# users must be able to create their own).
app.include_router(my_sources.router, prefix="/api", dependencies=_guard)
app.include_router(settings_api.router, prefix="/api", dependencies=_guard)
app.include_router(jobs.router, prefix="/api", dependencies=_guard)
app.include_router(fs.router, prefix="/api", dependencies=_guard)
app.include_router(ai_api.router, prefix="/api", dependencies=_guard)
app.include_router(logs.router, prefix="/api", dependencies=_guard)
from app.core.auth_guard import require_admin as _require_admin
app.include_router(backup.router, prefix="/api", dependencies=[Depends(_require_admin)])
from app.api.routes import software as software_routes
app.include_router(software_routes.router)
app.include_router(albums.router, prefix="/api", dependencies=_guard_ro)
from app.api.routes import relationships as relationships_routes
app.include_router(relationships_routes.router, prefix="/api", dependencies=_guard_ro)
from app.api.routes import chat as chat_routes
app.include_router(chat_routes.router, prefix="/api", dependencies=_guard)
from app.api.routes import shares as shares_routes
app.include_router(shares_routes.router, prefix="/api", dependencies=_guard_ro)        # manage (authed)
app.include_router(shares_routes.public_router, prefix="/api")                       # public (no guard)
from app.api.routes import highlights as highlights_routes
app.include_router(highlights_routes.router, prefix="/api", dependencies=_guard)

# ── iOS / mobile API v1 (also gated by enforce_auth) ─────────────────────────
app.include_router(v1_router.router, prefix="/api", dependencies=_guard)


@app.middleware("http")
async def add_version_header(request, call_next):
    response = await call_next(request)
    response.headers["X-PhotoFlow-Version"] = __version__
    return response


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": __version__}


@app.get("/api/version")
async def version():
    return {"version": __version__}
