"""Async database setup for Shiparr.

Responsabilités (guide):
- Initialiser SQLite async avec aiosqlite
- Créer les tables au démarrage si inexistantes
- Fournir une session factory
- Journal mode WAL pour performances
- Chemin configurable via Shiparr_DATA_PATH
"""

from __future__ import annotations

from pathlib import Path
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base ORM SQLAlchemy 2.0."""


async_engine: AsyncEngine | None = None
async_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_database_url(db_path: Path) -> str:
    """Build an async SQLite URL for the given path."""

    db_path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite+aiosqlite:///{db_path}"


async def init_engine(db_path: Path) -> AsyncEngine:
    """Initialise l'engine async et configure WAL."""

    global async_engine, async_session_factory

    url = get_database_url(db_path)
    engine = create_async_engine(url, future=True, echo=False)

    # Activer WAL et optimisations
    async with engine.begin() as conn:  # pragma: no cover - simple pragma
        await conn.exec_driver_sql("PRAGMA journal_mode=WAL")
        await conn.exec_driver_sql("PRAGMA busy_timeout=10000")
        await conn.exec_driver_sql("PRAGMA synchronous=NORMAL")

    async_engine = engine
    async_session_factory = async_sessionmaker(
        bind=engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )

    return engine


async def init_db(db_path: Path) -> None:
    """Crée les tables si nécessaires.

    Doit être appelé après avoir importé les modèles (pour que Base.metadata soit complet).
    """

    from . import models  # noqa: F401  # ensure models are imported

    if async_engine is None:
        await init_engine(db_path)

    assert async_engine is not None

    async with async_engine.begin() as conn:
        await conn.run_sync(models.Base.metadata.create_all)


async def get_session() -> AsyncIterator[AsyncSession]:
    """Fournit une session async (à utiliser avec async with)."""

    if async_session_factory is None:
        raise RuntimeError("Database not initialised. Call init_db() first.")

    session = async_session_factory()
    try:
        yield session
    finally:
        await session.close()


async def dispose_engine() -> None:
    """Ferme proprement l'engine."""

    global async_engine

    if async_engine is not None:
        await async_engine.dispose()
        async_engine = None
