import asyncio
import json

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from Shiparr.models import Base, Deployment, Project, Repository
from Shiparr.queue_manager import QueueManager


@pytest.mark.asyncio
async def test_priority(tmp_path, monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    deploy_calls = []
    async def fake_deploy(self, repo_id):
        deploy_calls.append(repo_id)
        
    monkeypatch.setattr("Shiparr.deployer.Deployer.deploy", fake_deploy)
    
    # Setup Repos
    async with async_session() as session:
        p = Project(name="p1", config_file="p1.yml")
        session.add(p)
        await session.flush()
        
        r1 = Repository(
            project_id=p.id,
            name="r1",
            git_url="u",
            branch="m",
            path="./",
            local_path="/tmp/1",
            check_interval=60
        )
        r2 = Repository(
            project_id=p.id,
            name="r2",
            git_url="u",
            branch="m",
            path="./",
            local_path="/tmp/2",
            check_interval=60
        )
        session.add_all([r1, r2])
        await session.commit()
        id1, id2 = r1.id, r2.id

    qm = QueueManager(session_factory=async_session)
    # Not starting worker yet to fill queue
    await qm.enqueue(id1, priority=10)
    await qm.enqueue(id2, priority=100) # Should go first
    
    await qm.start()
    await asyncio.sleep(0.5)
    await qm.stop()
    
    assert deploy_calls == [id2, id1]

@pytest.mark.asyncio
async def test_dependency_check(tmp_path, monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    deploy_calls = []
    async def fake_deploy(self, repo_id):
        deploy_calls.append(repo_id)
        return True
        
    monkeypatch.setattr("Shiparr.deployer.Deployer.deploy", fake_deploy)

    async with async_session() as session:
        p = Project(name="p1", config_file="p1.yml")
        session.add(p)
        await session.flush()
        
        repo2 = Repository(
            project_id=p.id, name="repo2", git_url="u", branch="m", path="./",
            local_path="/tmp/2", check_interval=60
        )
        session.add(repo2)
        await session.flush()
        
        repo1 = Repository(
            project_id=p.id, name="repo1", git_url="u", branch="m", path="./",
            local_path="/tmp/1", check_interval=60,
            depends_on=json.dumps(["repo2"])
        )
        session.add(repo1)
        await session.commit()
        r1_id, r2_id = repo1.id, repo2.id

    # Set retry delay short
    qm = QueueManager(session_factory=async_session, retry_delay=0.1)
    await qm.start()
    
    try:
        # Enqueue r1
        await qm.enqueue(r1_id, priority=10)
        
        # Wait a bit. r1 depends on r2. r2 not deployed.
        await asyncio.sleep(0.2)
        assert r1_id not in deploy_calls
        
        # Deploy r2
        async with async_session() as session:
            dep = Deployment(repository_id=r2_id, commit_hash="abc", status="success")
            session.add(dep)
            await session.commit()
            
        # Wait for retry
        await asyncio.sleep(0.2)
        assert r1_id in deploy_calls
        
    finally:
        await qm.stop()
