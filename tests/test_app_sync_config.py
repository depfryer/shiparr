from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from Shiparr.app import _sync_config_to_db
from Shiparr.config import LoadedConfig, ProjectConfig, RepositoryConfig, Settings
from Shiparr import database
from Shiparr.models import Base, Project, Repository


@pytest.mark.asyncio
async def test_sync_config_creates_projects_and_repos(tmp_path: Path) -> None:
    # Prepare in-memory DB
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    database.async_engine = engine
    database.async_session_factory = async_session

    # Build a simple LoadedConfig
    settings = Settings()
    repo_cfg = RepositoryConfig(
        name="media-stack",
        url="https://example.com/repo.git",
        branch="main",
        path="./",
        local_path=str(tmp_path / "media"),
        check_interval=60,
    )
    project_cfg = ProjectConfig(
        project="homelab",
        description="",
        tokens=None,
        repositories={"media-stack": repo_cfg},
    )
    loaded = LoadedConfig(settings=settings, projects={"homelab": project_cfg})

    await _sync_config_to_db(loaded)

    async with async_session() as session:
        projects = (await session.execute(select(Project))).scalars().all()
        repos = (await session.execute(select(Repository))).scalars().all()

    assert len(projects) == 1
    assert projects[0].name == "homelab"
    assert len(repos) == 1
    assert repos[0].name == "media-stack"


@pytest.mark.asyncio
async def test_sync_config_shared_local_path_conflict(tmp_path: Path, caplog) -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    database.async_engine = engine
    database.async_session_factory = async_session

    settings = Settings()
    local = str(tmp_path / "shared")

    repo1 = RepositoryConfig(
        name="repo1",
        url="https://example.com/repo1.git",
        branch="main",
        path="./",
        local_path=local,
        check_interval=60,
    )
    repo2 = RepositoryConfig(
        name="repo2",
        url="https://example.com/repo2.git",  # different URL -> conflict
        branch="main",
        path="./",
        local_path=local,
        check_interval=60,
    )

    p1 = ProjectConfig(project="p1", description="", tokens=None, repositories={"repo1": repo1})
    p2 = ProjectConfig(project="p2", description="", tokens=None, repositories={"repo2": repo2})
    loaded = LoadedConfig(settings=settings, projects={"p1": p1, "p2": p2})

    with caplog.at_level("WARNING"):
        await _sync_config_to_db(loaded)

    # Only the first repo should be created, the conflicting one skipped
    async with async_session() as session:
        repos = (await session.execute(select(Repository))).scalars().all()

    assert len(repos) == 1
    assert repos[0].name == "repo1"
    assert any("Conflicting repository configuration" in rec.message for rec in caplog.records)


@pytest.mark.asyncio
async def test_sync_config_shared_local_path_success(tmp_path: Path, caplog) -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    database.async_engine = engine
    database.async_session_factory = async_session

    settings = Settings()
    local = str(tmp_path / "shared")

    repo1 = RepositoryConfig(
        name="repo1",
        url="https://example.com/repo.git",
        branch="main",
        path="./",
        local_path=local,
        check_interval=60,
    )
    repo2 = RepositoryConfig(
        name="repo2",
        url="https://example.com/repo.git",
        branch="main",
        path="./",
        local_path=local,
        check_interval=60,
    )

    p1 = ProjectConfig(project="p1", description="", tokens=None, repositories={"repo1": repo1})
    p2 = ProjectConfig(project="p2", description="", tokens=None, repositories={"repo2": repo2})
    loaded = LoadedConfig(settings=settings, projects={"p1": p1, "p2": p2})

    with caplog.at_level("INFO"):
        await _sync_config_to_db(loaded)

    async with async_session() as session:
        repos = (await session.execute(select(Repository))).scalars().all()

    # Both repos should exist because they share valid config
    assert len(repos) == 2
    repo_names = {r.name for r in repos}
    assert "repo1" in repo_names
    assert "repo2" in repo_names

    # Verify log message about mutualisation
    assert any(
        "Multiple repositories share the same Git local_path" in rec.message
        for rec in caplog.records
    )
