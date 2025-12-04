import pytest
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from Shiparr.deployer import Deployer
from Shiparr.models import Repository, Base
from Shiparr.git_manager import GitManager

@pytest.mark.asyncio
async def test_deploy_prune_enabled(tmp_path, monkeypatch):
    # Setup DB
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as session:
        repo = Repository(
            project_id=1, name="repo", git_url="u", branch="m", path="./",
            local_path=str(tmp_path/"repo"), check_interval=60, last_commit_hash="abc"
        )
        session.add(repo)
        await session.flush()

        # Mock Git/Docker
        async def fake_remote_hash(local_path, branch): return "def"
        async def fake_pull(local_path, branch="main"): return "def"
        async def fake_clone(*args, **kwargs): pass
        async def fake_local_hash(local_path): return "def"
        
        monkeypatch.setattr("Shiparr.git_manager.GitManager.get_remote_hash", fake_remote_hash)
        monkeypatch.setattr("Shiparr.git_manager.GitManager.pull", fake_pull)
        monkeypatch.setattr("Shiparr.git_manager.GitManager.clone", fake_clone)
        monkeypatch.setattr("Shiparr.git_manager.GitManager.get_local_hash", fake_local_hash)

        prune_called = False
        async def fake_exec(*args, **kwargs):
            nonlocal prune_called
            if "prune" in args:
                prune_called = True
            
            class P:
                returncode = 0
                async def communicate(self): return b"ok", b""
            return P()
        monkeypatch.setattr("asyncio.create_subprocess_exec", fake_exec)

        deployer = Deployer(session=session, prune_enabled=True)
        await deployer.deploy(repo.id)
        
        assert prune_called

@pytest.mark.asyncio
async def test_deploy_prune_disabled(tmp_path, monkeypatch):
    # Setup DB
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as session:
        repo = Repository(
            project_id=1, name="repo", git_url="u", branch="m", path="./",
            local_path=str(tmp_path/"repo"), check_interval=60, last_commit_hash="abc"
        )
        session.add(repo)
        await session.flush()

        # Mock Git/Docker
        async def fake_remote_hash(local_path, branch): return "def"
        async def fake_pull(local_path, branch="main"): return "def"
        async def fake_clone(*args, **kwargs): pass
        async def fake_local_hash(local_path): return "def"
        
        monkeypatch.setattr("Shiparr.git_manager.GitManager.get_remote_hash", fake_remote_hash)
        monkeypatch.setattr("Shiparr.git_manager.GitManager.pull", fake_pull)
        monkeypatch.setattr("Shiparr.git_manager.GitManager.clone", fake_clone)
        monkeypatch.setattr("Shiparr.git_manager.GitManager.get_local_hash", fake_local_hash)

        prune_called = False
        async def fake_exec(*args, **kwargs):
            nonlocal prune_called
            if "prune" in args:
                prune_called = True
            class P:
                returncode = 0
                async def communicate(self): return b"ok", b""
            return P()
        monkeypatch.setattr("asyncio.create_subprocess_exec", fake_exec)

        deployer = Deployer(session=session, prune_enabled=False)
        await deployer.deploy(repo.id)
        
        assert not prune_called
