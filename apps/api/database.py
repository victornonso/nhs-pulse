from contextlib import contextmanager, asynccontextmanager
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.engine import make_url
import ssl
from .settings import settings

writer = create_engine(
    settings.worker_database_url or settings.migration_database_url,
    pool_pre_ping=True,
    pool_size=3,
    max_overflow=2,
)
reader_url = make_url(settings.database_url).set(drivername="postgresql+asyncpg")
secure = reader_url.query.get("sslmode") not in (None, "disable")
reader_url = reader_url.difference_update_query(["sslmode", "channel_binding"])
async_engine = create_async_engine(
    reader_url,
    connect_args={"ssl": ssl.create_default_context()} if secure else {},
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
