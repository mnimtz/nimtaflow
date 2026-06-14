from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.database import init_db, _engine
from app.api.routes import auth, photos, people, sources, settings_api, jobs
from app.api.routes import fs, ai_api, logs, backup, albums
from app.api.v1 import router as v1_router


# Idempotent column additions applied on every startup (Postgres ADD COLUMN IF NOT EXISTS).
_COLUMN_MIGRATIONS = [
    "ALTER TABLE photo_sources ADD COLUMN IF NOT EXISTS scan_interval_minutes INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE photo_sources ADD COLUMN IF NOT EXISTS detect_deletions BOOLEAN NOT NULL DEFAULT TRUE",
    "ALTER TABLE photos ADD COLUMN IF NOT EXISTS is_missing BOOLEAN NOT NULL DEFAULT FALSE",
    "ALTER TABLE photos ADD COLUMN IF NOT EXISTS missing_at TIMESTAMPTZ",
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
    version="1.0.0",
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


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}
