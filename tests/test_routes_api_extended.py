from __future__ import annotations

from datetime import datetime

import pytest
from quart import Quart
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from Shiparr.config import Settings
from Shiparr.models import Base, Deployment, Project, Repository
from Shiparr.routes import api


@pytest.mark.asyncio
async def test_list_projects_and_get_project(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as session:
        # Seed one project, one repo, one deployment
        project = Project(name="homelab", config_file="homelab.yaml")
        session.add(project)
        await session.flush()

        repo = Repository(
            project_id=project.id,
            name="media-stack",
            git_url="https://example.com/repo.git",
            branch="main",
            path="./",
            local_path="/tmp/media-stack",
            check_interval=60,
        )
        session.add(repo)
        await session.flush()

        dep = Deployment(
            repository_id=repo.id,
            commit_hash="abc",
            status="success",
            started_at=datetime.utcnow(),
            finished_at=datetime.utcnow(),
            logs="ok",
        )
        session.add(dep)
        await session.commit()

        async def fake_get_session():
            # Minimal async generator compatible avec `async for session in get_session()`
            yield session

        monkeypatch.setattr("Shiparr.routes.api.get_session", fake_get_session)

        app = Quart(__name__)
        settings = Settings()
        settings.auth_enabled = False
        app.config["Shiparr_SETTINGS"] = settings

        # list_projects
        async with app.test_request_context("/api/projects"):
            resp = await api.list_projects()
            data = await resp.get_json()
            assert len(data) == 1
            assert data[0]["name"] == "homelab"

        # get_project
        async with app.test_request_context("/api/projects/homelab"):
            resp2 = await api.get_project("homelab")
            data2 = await resp2.get_json()
        assert data2["name"] == "homelab"
        assert len(data2["repositories"]) == 1
        assert data2["repositories"][0]["name"] == "media-stack"


@pytest.mark.asyncio
async def test_get_repository_and_deployments(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as session:
        project = Project(name="homelab", config_file="homelab.yaml")
        session.add(project)
        await session.flush()

        repo = Repository(
            project_id=project.id,
            name="media-stack",
            git_url="https://example.com/repo.git",
            branch="main",
            path="./",
            local_path="/tmp/media-stack",
            check_interval=60,
        )
        session.add(repo)
        await session.flush()

        dep = Deployment(
            repository_id=repo.id,
            commit_hash="abc",
            status="success",
            started_at=datetime.utcnow(),
            finished_at=datetime.utcnow(),
            logs="ok",
        )
        session.add(dep)
        await session.commit()

        async def fake_get_session():
            yield session

        monkeypatch.setattr("Shiparr.routes.api.get_session", fake_get_session)

        app = Quart(__name__)
        settings = Settings()
        settings.auth_enabled = False
        app.config["Shiparr_SETTINGS"] = settings

        async with app.test_request_context(f"/api/repositories/{repo.id}"):
            resp = await api.get_repository(repo.id)
            data = await resp.get_json()
            assert data["name"] == "media-stack"

        async with app.test_request_context(f"/api/repositories/{repo.id}/deployments"):
            resp2 = await api.list_deployments(repo.id)
            data2 = await resp2.get_json()
        assert len(data2) == 1
        assert data2[0]["commit_hash"] == "abc"