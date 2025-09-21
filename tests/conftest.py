"""
Pytest configuration for the application
"""
import asyncio
import os
from typing import AsyncGenerator, Generator

import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
import httpx
from sqlalchemy.ext.asyncio import (
    AsyncSession, async_sessionmaker, create_async_engine
)

from src.core.config import settings
from src.db.base import Base
from src.db.session import get_db
from src.main import create_application


# Set test environment and override runtime settings to avoid external deps
os.environ["ENV"] = "test"
settings.ENV = "test"
settings.scheduler.enabled = False
settings.cache.backend_type = "memory"
settings.DATABASE_URI = "sqlite+aiosqlite:///./test_app.db"


@pytest.fixture(scope="session")
def event_loop() -> Generator:
    """
    Create an instance of the event loop for each test session.
    """
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def test_app(test_db_engine) -> AsyncGenerator[FastAPI, None]:
    """
    Create a FastAPI test application.
    """
    app = create_application()
    session_factory = async_sessionmaker(test_db_engine, expire_on_commit=False)

    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            try:
                yield session
            finally:
                await session.rollback()

    app.dependency_overrides[get_db] = _override_get_db
    async with LifespanManager(app):
        yield app


@pytest_asyncio.fixture(scope="session")
async def test_db_engine():
    """
    Create a test database engine.
    """
    # Create a new test database URL
    base_uri = str(settings.DATABASE_URI)
    TEST_DATABASE_URL = base_uri.replace(
        f"/{settings.POSTGRES_DB}", "/test_db"
    )
    
    # Create engine for test database
    engine = create_async_engine(TEST_DATABASE_URL, echo=True)
    
    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    
    yield engine
    
    # Drop all tables after tests
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    
    # Dispose engine
    await engine.dispose()


@pytest_asyncio.fixture
async def test_db(test_app: FastAPI, test_db_engine) -> AsyncGenerator[AsyncSession, None]:
    """
    Create a new database session for a test.
    """
    # Create test session
    connection = await test_db_engine.connect()
    transaction = await connection.begin()

    # Use session factory
    test_session_factory = async_sessionmaker(
        connection, expire_on_commit=False
    )

    # Create a session
    async with test_session_factory() as session:
        previous_override = test_app.dependency_overrides.get(get_db)

        async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
            yield session

        test_app.dependency_overrides[get_db] = _override_get_db

        try:
            yield session
        finally:
            if previous_override is not None:
                test_app.dependency_overrides[get_db] = previous_override
            else:
                test_app.dependency_overrides.pop(get_db, None)

    # Rollback the transaction
    await transaction.rollback()
    await connection.close()


@pytest_asyncio.fixture
async def client(test_app: FastAPI) -> AsyncGenerator[httpx.AsyncClient, None]:
    """
    Create an async HTTP client for testing.
    """
    transport = httpx.ASGITransport(app=test_app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as client:
        yield client
