from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.database import init_db, _engine
from app.core.config import get_settings
from app.api.routes import auth, photos, people, sources, settings_api, jobs


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    # Run migrations on startup
    from alembic.config import Config
    from alembic import command
    import asyncio, os
    alembic_cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    await asyncio.to_thread(command.upgrade, alembic_cfg, "head")
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


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}
