import os

os.environ["DATABASE_URL"] = "postgresql+asyncpg://payments:payments@localhost:5432/payments_test"
os.environ["RABBITMQ_URL"] = "amqp://guest:guest@localhost:5672/"
os.environ["API_KEY"] = "test-api-key"
os.environ["OUTBOX_POLL_INTERVAL_SEC"] = "0.2"

import app.config as config_module
from app.config import Settings

config_module.settings = Settings()

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db import Base, get_session
from app.models.outbox import Outbox  # noqa: F401
from app.models.payment import Payment  # noqa: F401

TEST_DATABASE_URL = os.environ["DATABASE_URL"]
API_KEY = os.environ["API_KEY"]


@pytest_asyncio.fixture
async def engine():
    eng = create_async_engine(TEST_DATABASE_URL, pool_pre_ping=True)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine):
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


@pytest_asyncio.fixture
async def session(session_factory) -> AsyncGenerator[AsyncSession, None]:
    async with session_factory() as s:
        yield s


@pytest_asyncio.fixture
async def client(engine, session_factory, monkeypatch):
    import app.db as db_module
    import app.consumer.handler as handler_module

    db_module.engine = engine
    db_module.SessionLocal = session_factory
    handler_module.SessionLocal = session_factory

    from app.main import app

    @asynccontextmanager
    async def _lifespan(_app):
        yield

    app.router.lifespan_context = _lifespan

    async def _override_session() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as s:
            yield s

    app.dependency_overrides[get_session] = _override_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {"X-API-Key": API_KEY}


@pytest.fixture
def payment_body() -> dict:
    return {
        "amount": "100.50",
        "currency": "RUB",
        "description": "test payment",
        "metadata": {"order_id": "1"},
        "webhook_url": "https://example.com/hook",
    }
