from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware

from app.core.database import init_db, _engine
from app.version import __version__
from app.api.routes import auth, photos, people, sources, settings_api, jobs
from app.api.routes import fs, ai_api, logs, backup, albums
from app.api.v1 import router as v1_router


# Idempotent schema migrations applied on every startup.
# create_all() only creates *missing tables* — it never ALTERs an existing table,
# so any column added to a model after its table first existed must be added here.
# Each entry must be a single SQL statement (DO $$..$$ blocks count as one).
_COLUMN_MIGRATIONS = [
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
        ADD COLUMN IF NOT EXISTS description_model    VARCHAR(128),
        ADD COLUMN IF NOT EXISTS video_fps            FLOAT,
        ADD COLUMN IF NOT EXISTS video_bitrate        INTEGER,
        ADD COLUMN IF NOT EXISTS user_description     TEXT""",
    # ── photos: folder-watch / deletion detection ─────────────────────────────
    "ALTER TABLE photos ADD COLUMN IF NOT EXISTS is_missing BOOLEAN NOT NULL DEFAULT FALSE",
    "ALTER TABLE photos ADD COLUMN IF NOT EXISTS missing_at TIMESTAMPTZ",
    "ALTER TABLE photos ADD COLUMN IF NOT EXISTS video_preview_path VARCHAR(512)",
    "ALTER TABLE photos ADD COLUMN IF NOT EXISTS ai_error BOOLEAN NOT NULL DEFAULT FALSE",
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
    # ── users: defensive (in case the table predates these columns) ───────────
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS access_config JSONB",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS totp_secret VARCHAR(64)",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS totp_enabled BOOLEAN NOT NULL DEFAULT FALSE",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_login TIMESTAMPTZ",
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
    async with _engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
        # Lightweight column migrations (create_all never ALTERs existing tables).
        for stmt in _COLUMN_MIGRATIONS:
            await conn.execute(text(stmt))

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
from app.core.auth_guard import enforce_auth
app.include_router(auth.router, prefix="/api")
app.include_router(users_routes.router, prefix="/api")

# ── Remote worker API (own shared-token auth, NOT user-guarded) ──────────────
from app.api.routes import remote as remote_routes
app.include_router(remote_routes.router, prefix="/api")

# ── Web data routes — gated by enforce_auth (no-op until auth.enforce=true) ──
_guard = [Depends(enforce_auth)]
app.include_router(photos.router, prefix="/api", dependencies=_guard)
app.include_router(people.router, prefix="/api", dependencies=_guard)
app.include_router(sources.router, prefix="/api", dependencies=_guard)
app.include_router(settings_api.router, prefix="/api", dependencies=_guard)
app.include_router(jobs.router, prefix="/api", dependencies=_guard)
app.include_router(fs.router, prefix="/api", dependencies=_guard)
app.include_router(ai_api.router, prefix="/api", dependencies=_guard)
app.include_router(logs.router, prefix="/api", dependencies=_guard)
from app.core.auth_guard import require_admin as _require_admin
app.include_router(backup.router, prefix="/api", dependencies=[Depends(_require_admin)])
app.include_router(albums.router, prefix="/api", dependencies=_guard)
from app.api.routes import relationships as relationships_routes
app.include_router(relationships_routes.router, prefix="/api", dependencies=_guard)
from app.api.routes import chat as chat_routes
app.include_router(chat_routes.router, prefix="/api", dependencies=_guard)
from app.api.routes import shares as shares_routes
app.include_router(shares_routes.router, prefix="/api", dependencies=_guard)        # manage (authed)
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
