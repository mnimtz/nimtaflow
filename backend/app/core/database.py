import sys
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool
from .config import get_settings


class Base(DeclarativeBase):
    pass


def _is_celery_worker() -> bool:
    """True inside a Celery worker/beat process. Those run each task on a NEW event
    loop, so a pooled (loop-bound) asyncpg connection breaks ("Event loop is closed")
    → they MUST use NullPool. The web backend runs ONE persistent loop and uses a
    bounded pool instead (see get_engine)."""
    argv = " ".join(sys.argv).lower()
    return "celery" in argv


def get_engine():
    settings = get_settings()
    # Per-connection safety nets (apply to BOTH web + workers): Postgres reaps a
    # connection left idle-in-transaction > 60s or simply idle > 5min, so a leaked
    # session can never pile up to "too many clients" or hold locks. pool_pre_ping
    # then transparently replaces any reaped connection.
    if _is_celery_worker():
        # Worker: NullPool. A bounded async pool here broke long-running tasks with
        # "MissingGreenlet: greenlet_spawn has not been called" (pool pre_ping/recycle
        # do connection IO outside the per-task greenlet on the fresh event loops
        # Celery creates per task) — which crashed the library scan mid-run. NullPool
        # avoids cross-loop reuse entirely. The connection LEAK under heavy load is
        # now contained primarily by shutdown_asyncgens() in _run() — so we DON'T
        # need aggressive idle reaping here. Aggressive 60s reaping actually KILLED
        # the long library scan: the scan walks the tree + runs deletion-detection
        # (an os.path.exists loop over all photos under the root) with long gaps
        # between DB ops; a 60s idle_session reap killed its connection mid-scan and
        # the next query crashed, so the big folders never got indexed. Generous
        # timeouts here let long tasks run; shutdown_asyncgens still frees sessions.
        worker_connect_args = {"server_settings": {
            "idle_in_transaction_session_timeout": "300000",  # 5min (covers deletion-detection loop)
            "idle_session_timeout": "600000",                 # 10min — backstop only
        }}
        return create_async_engine(settings.database_url, echo=False,
                                   poolclass=NullPool, connect_args=worker_connect_args)
    connect_args = {"server_settings": {
        "idle_in_transaction_session_timeout": "60000",   # 60s
        "idle_session_timeout": "60000",                  # 60s — reap leaked idle conns
    }}
    # Web backend: a BOUNDED pool on its single persistent loop. Hard ceiling of
    # pool_size + max_overflow connections means the API can NEVER exhaust Postgres,
    # regardless of any session leak — the structural fix for the recurring
    # "too many clients" lockouts. pre_ping drops connections the server reaped while
    # idle; recycle proactively refreshes them before that happens.
    return create_async_engine(
        settings.database_url, echo=False,
        pool_size=10, max_overflow=10, pool_timeout=30,
        pool_pre_ping=True, pool_recycle=180,
        connect_args=connect_args,
    )


def get_session_factory(engine):
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


_engine = None
_session_factory = None


def init_db():
    global _engine, _session_factory
    _engine = get_engine()
    _session_factory = get_session_factory(_engine)


async def get_db():
    async with _session_factory() as session:
        try:
            yield session
        finally:
            await session.close()


async def dispose_db():
    """Close the async engine + all its connections ON THE CURRENT EVENT LOOP.

    Celery tasks each run on a fresh event loop (worker._run). asyncpg connections
    are loop-bound, so an engine left undisposed when its loop closes leaks the
    connection — the garbage collector then tries to close it on a dead loop
    ("Event loop is closed" / "non-checked-in connection"), and a later task reusing
    a half-torn-down connection hit "another operation in progress". Disposing here,
    inside the task's own loop, frees everything cleanly before the loop closes; the
    next task's init_db() builds a fresh engine on its own loop."""
    global _engine, _session_factory
    eng = _engine
    _engine = None
    _session_factory = None
    if eng is not None:
        await eng.dispose()
