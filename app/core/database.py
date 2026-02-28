from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy import create_engine
from contextlib import contextmanager

from app.core.config import get_settings

settings = get_settings()

# PostgreSQL URL 변환
# Sync: postgresql://...  (psycopg2)
# Async: postgresql+asyncpg://...
_sync_url = settings.database_url
_async_url = _sync_url.replace("postgresql://", "postgresql+asyncpg://", 1)

# Async engine (for FastAPI)
engine = create_async_engine(
    _async_url,
    echo=settings.debug,
)

async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# Sync engine (for crawling services)
sync_engine = create_engine(
    _sync_url,
    echo=settings.debug,
    pool_size=5,
    max_overflow=10,
)

SyncSessionLocal = sessionmaker(
    bind=sync_engine,
    autocommit=False,
    autoflush=False,
)

Base = declarative_base()


async def get_db() -> AsyncSession:
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()


@contextmanager
def get_sync_db():
    """동기 DB 세션 (크롤링 서비스용)"""
    db = SyncSessionLocal()
    try:
        yield db
    finally:
        db.close()
