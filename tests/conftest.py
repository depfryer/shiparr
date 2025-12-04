"""Pytest fixtures for Shiparr tests."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import AsyncIterator

import pytest
from quart import Quart
from sqlalchemy.ext.asyncio import AsyncSession

from Shiparr.app import create_app
from Shiparr.database import async_session_factory, dispose_engine, init_db


@pytest.fixture(autouse=True)
async def cleanup_engine():
    yield
    await dispose_engine()

@pytest.fixture(scope="session")
def event_loop():  # type: ignore[override]
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture()
async def app(tmp_path: Path, monkeypatch) -> AsyncIterator[Quart]:
    # Configure Shiparr_DATA_PATH pour utiliser tmp_path
    await dispose_engine()
    monkeypatch.setenv("Shiparr_DATA_PATH", str(tmp_path))
    monkeypatch.setenv("Shiparr_CONFIG_PATH", str(tmp_path / "config"))
    app = create_app()
    yield app
    await dispose_engine()


@pytest.fixture()
async def client(app: Quart):
    async with app.test_app() as test_app:
        yield test_app.test_client()


@pytest.fixture()
async def db_session(tmp_path: Path) -> AsyncIterator[AsyncSession]:
    db_path = tmp_path / "test.db"
    await init_db(db_path)
    assert async_session_factory is not None
    async with async_session_factory() as session:
        yield session
    await dispose_engine()


@pytest.fixture()
def sample_project_config(tmp_path: Path) -> Path:
    cfg = tmp_path / "homelab.yaml"
    cfg.write_text(
        """project: homelab
repositories:
  media-stack:
    url: https://example.com/repo.git
    branch: main
    path: ./
    local_path: /tmp/media-stack
    check_interval: 60
""",
        encoding="utf-8",
    )
    return cfg
