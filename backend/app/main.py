from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.database import init_db, _engine
from app.core.config import get_settings
from app.api.routes import auth, photos, people, sources, settings_api, jobs
from app.api.routes import fs


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    # Create tables directly — no alembic needed for initial deploy
    from app.core.database import Base, _engine
    import app.models  # noqa — ensure all models are imported
    async with _engine.begin() as conn:
        # Enable pgvector extension first
        await conn.execute(__import__("sqlalchemy").text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
    yield
    if _engine:
        await _engine.dispose()


app = FastAPI(title="PhotoFlow", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api")
app.include_router(photos.router, prefix="/api")
app.include_router(people.router, prefix="/api")
app.include_router(sources.router, prefix="/api")
app.include_router(settings_api.router, prefix="/api")
app.include_router(jobs.router, prefix="/api")
app.include_router(fs.router, prefix="/api")


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}
