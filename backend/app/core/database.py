from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool
from .config import get_settings


class Base(DeclarativeBase):
    pass


def get_engine():
    settings = get_settings()
    return create_async_engine(
        settings.database_url, echo=False,
        # NullPool = NO connection pooling: every checkout opens a fresh asyncpg
        # connection and closes it on release. This is the correct pool for our
        # Celery tasks, which run each on a NEW event loop (see worker._run): a
        # POOLED connection is bound to the loop it was created on, so reusing it
        # from the next task's loop raised "Event loop is closed" and leaked the
        # connection — those leaked up to Postgres "too many clients", which made
        # the API return nothing (empty pages). No pool → nothing to leak across
        # loops. The tiny per-request connect cost is irrelevant for this app.
        poolclass=NullPool,
        connect_args={"server_settings": {
            # Safety net: Postgres auto-terminates any session left
            # idle-in-transaction > 60s. A session that isn't cleanly closed (e.g.
            # `async for db in get_db(): … return` whose async generator isn't
            # aclosed before a short-lived event loop closes in a Celery task) then
            # can't pile up + hold table locks — that once blocked an ALTER TABLE
            # migration and hung backend startup. Also caps the "too many clients" leak.
            "idle_in_transaction_session_timeout": "60000",  # ms
        }},
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
