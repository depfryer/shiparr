from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from Shiparr.deployer import Deployer
from Shiparr.models import Base, Repository


@pytest.mark.asyncio
async def test_healthcheck_success(tmp_path: Path, monkeypatch):
    # Setup DB
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Setup Repo
    async with async_session() as session:
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        
        repo = Repository(
            project_id=1,
            name="repo",
            git_url="https://example.com/repo.git",
            branch="main",
            path="./",
            local_path=str(repo_dir),
            check_interval=60,
            last_commit_hash="abc",
            healthcheck_url="http://localhost:8080/health",
            healthcheck_timeout=2,
            healthcheck_expected_status=200
        )
        session.add(repo)
        await session.flush()

        # Mock Git
        async def fake_remote_hash(local_path, branch):
            return "def" # Force update
        async def fake_pull(local_path, branch="main"):
            return "def"
        async def fake_clone(url, branch, local_path):
            pass
        async def fake_local_hash(local_path):
            return "def"

        monkeypatch.setattr("Shiparr.git_manager.GitManager.get_remote_hash", fake_remote_hash)
        monkeypatch.setattr("Shiparr.git_manager.GitManager.pull", fake_pull)
        monkeypatch.setattr("Shiparr.git_manager.GitManager.clone", fake_clone)
        monkeypatch.setattr("Shiparr.git_manager.GitManager.get_local_hash", fake_local_hash)

        # Mock Docker
        async def fake_exec(*args, **kwargs):
            class P:
                returncode = 0
                async def communicate(self):
                    return b"ok", b""
            return P()
        monkeypatch.setattr("asyncio.create_subprocess_exec", fake_exec)

        # Mock HTTPX
        class MockResponse:
            status_code = 200

        class MockClient:
            def __init__(self, verify=False):
                pass
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                pass
            async def get(self, url, timeout=None):
                return MockResponse()

        monkeypatch.setattr("httpx.AsyncClient", MockClient)

        deployer = Deployer(session=session)
        dep = await deployer.deploy(repo.id)
        
        assert dep.status == "success"
        assert "Healthcheck passed" in dep.logs

@pytest.mark.asyncio
async def test_healthcheck_failure(tmp_path: Path, monkeypatch):
    # Setup DB
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Setup Repo
    async with async_session() as session:
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        
        repo = Repository(
            project_id=1,
            name="repo",
            git_url="https://example.com/repo.git",
            branch="main",
            path="./",
            local_path=str(repo_dir),
            check_interval=60,
            last_commit_hash="abc",
            healthcheck_url="http://localhost:8080/health",
            healthcheck_timeout=1, # Short timeout
            healthcheck_expected_status=200
        )
        session.add(repo)
        await session.flush()

        # Mock Git
        async def fake_remote_hash(local_path, branch):
            return "def" # Force update
        async def fake_pull(local_path, branch="main"):
            return "def"
        async def fake_clone(url, branch, local_path):
            pass
        async def fake_local_hash(local_path):
            return "def"

        monkeypatch.setattr("Shiparr.git_manager.GitManager.get_remote_hash", fake_remote_hash)
        monkeypatch.setattr("Shiparr.git_manager.GitManager.pull", fake_pull)
        monkeypatch.setattr("Shiparr.git_manager.GitManager.clone", fake_clone)
        monkeypatch.setattr("Shiparr.git_manager.GitManager.get_local_hash", fake_local_hash)

        # Mock Docker
        async def fake_exec(*args, **kwargs):
            class P:
                returncode = 0
                async def communicate(self):
                    return b"ok", b""
            return P()
        monkeypatch.setattr("asyncio.create_subprocess_exec", fake_exec)

        # Mock HTTPX to always fail or return 500
        class MockResponse:
            status_code = 500

        class MockClient:
            def __init__(self, verify=False):
                pass
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                pass
            async def get(self, url, timeout=None):
                return MockResponse()

        monkeypatch.setattr("httpx.AsyncClient", MockClient)

        deployer = Deployer(session=session)
        dep = await deployer.deploy(repo.id)
        
        assert dep.status == "failed"
        assert "Healthcheck failed" in dep.logs
