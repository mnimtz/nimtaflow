from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from .config import get_settings


class Base(DeclarativeBase):
    pass


def get_engine():
    settings = get_settings()
    return create_async_engine(
        settings.database_url, echo=False,
        pool_pre_ping=True,   # drop dead connections instead of erroring on them
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
