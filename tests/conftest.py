import os
from collections.abc import AsyncIterator

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/test_db")
os.environ.setdefault("DATABASE_URL_SYNC", "postgresql+psycopg2://postgres:postgres@localhost:5432/test_db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("CELERY_BROKER_URL", "memory://")
os.environ.setdefault("CELERY_RESULT_BACKEND", "cache+memory://")

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.session import get_db


@pytest_asyncio.fixture(scope="session")
async def async_engine():
    pg = pytest.importorskip("testcontainers.postgres")
    with pg.PostgresContainer("postgres:16-alpine") as container:
        url = container.get_connection_url().replace("psycopg2", "asyncpg")
        engine = create_async_engine(url, future=True)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        try:
            yield engine
        finally:
            await engine.dispose()


@pytest_asyncio.fixture
async def db_session(async_engine) -> AsyncIterator[AsyncSession]:
    maker = async_sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)
    async with maker() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def client(async_engine) -> AsyncIterator[AsyncClient]:
    from app.main import app

    maker = async_sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)

    async def _override() -> AsyncIterator[AsyncSession]:
        async with maker() as session:
            yield session

    app.dependency_overrides[get_db] = _override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
