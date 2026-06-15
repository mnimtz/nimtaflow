from contextlib import asynccontextmanager
from fastapi import FastAPI
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
    # ── photo_sources: watching ───────────────────────────────────────────────
    "ALTER TABLE photo_sources ADD COLUMN IF NOT EXISTS scan_interval_minutes INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE photo_sources ADD COLUMN IF NOT EXISTS detect_deletions BOOLEAN NOT NULL DEFAULT TRUE",
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
]


@asynccontextmanager
async def lifespan(app: FastAPI):
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

# ── Legacy/web routes ────────────────────────────────────────────────────────
app.include_router(auth.router, prefix="/api")
app.include_router(photos.router, prefix="/api")
app.include_router(people.router, prefix="/api")
app.include_router(sources.router, prefix="/api")
app.include_router(settings_api.router, prefix="/api")
app.include_router(jobs.router, prefix="/api")
app.include_router(fs.router, prefix="/api")
app.include_router(ai_api.router, prefix="/api")
app.include_router(logs.router, prefix="/api")
app.include_router(backup.router, prefix="/api")
app.include_router(albums.router, prefix="/api")

# ── iOS / mobile API v1 ──────────────────────────────────────────────────────
app.include_router(v1_router.router, prefix="/api")


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
