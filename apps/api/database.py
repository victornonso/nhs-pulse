from contextlib import contextmanager, asynccontextmanager
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import create_async_engine
from .settings import settings

writer = create_engine(
    settings.worker_database_url or settings.migration_database_url,
    pool_pre_ping=True,
    pool_size=3,
    max_overflow=2,
)
async_engine = create_async_engine(
    settings.database_url.replace("postgresql+psycopg://", "postgresql+asyncpg://"),
    pool_pre_ping=True,
    pool_size=4,
    max_overflow=2,
)


@contextmanager
def transaction():
    with writer.begin() as conn:
        conn.execute(text("SET LOCAL statement_timeout='90s'"))
        yield conn


@asynccontextmanager
async def read_session():
    async with async_engine.begin() as conn:
        await conn.execute(text("SET LOCAL statement_timeout='15s'"))
        yield conn


def records(conn, sql, parameters=None):
    return [dict(r) for r in conn.execute(text(sql), parameters or {}).mappings()]


async def fetch(conn, sql, parameters=None):
    return [
        dict(r) for r in (await conn.execute(text(sql), parameters or {})).mappings()
    ]
