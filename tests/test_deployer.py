from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from Shiparr.config import LoadedConfig, ProjectConfig, RepositoryConfig, Settings
from Shiparr.deployer import Deployer
from Shiparr.models import Base, Deployment, Project, Repository
from Shiparr.notifications import NotificationManager


@pytest.mark.asyncio
async def test_deploy_no_changes(tmp_path: Path, monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as session:
        repo = Repository(
            project_id=1,
            name="repo",
            git_url="https://example.com/repo.git",
            branch="main",
            path="./",
            local_path=str(tmp_path / "repo"),
            check_interval=60,
            last_commit_hash="abc",
        )
        session.add(repo)
        await session.flush()

        async def fake_remote_hash(local_path, branch):  # type: ignore[unused-argument]
            return "abc"

        from Shiparr import git_manager

        git_manager.GitManager.get_remote_hash = fake_remote_hash  # type: ignore[assignment]

        # Simuler des conteneurs déjà en cours d'exécution pour ne pas forcer un déploiement
        async def fake_check(self, workdir, env):  # type: ignore[unused-argument]
            return True

        monkeypatch.setattr(
            "Shiparr.deployer.Deployer._check_containers_running",
            fake_check,
        )

        deployer = Deployer(session=session)
        dep = await deployer.deploy(repo.id)
        assert dep.status == "success"
        assert dep.logs == "No changes, services running"


@pytest.mark.asyncio
async def test_deploy_with_changes(tmp_path: Path, monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as session:
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        # Rendre le dossier non vide pour éviter le chemin de clonage initial
        (repo_dir / "dummy.txt").write_text("x", encoding="utf-8")

        repo = Repository(
            project_id=1,
            name="repo",
            git_url="https://example.com/repo.git",
            branch="main",
            path="./",
            local_path=str(repo_dir),
            check_interval=60,
            last_commit_hash="abc",
        )
        session.add(repo)
        await session.flush()

        from Shiparr import git_manager

        async def fake_remote_hash(local_path, branch):  # type: ignore[unused-argument]
            return "def"

        async def fake_pull(local_path, branch="main"):  # type: ignore[unused-argument]
            return "def"

        git_manager.GitManager.get_remote_hash = fake_remote_hash  # type: ignore[assignment]
        git_manager.GitManager.pull = fake_pull  # type: ignore[assignment]

        async def fake_exec(*args, **kwargs):  # type: ignore[unused-argument]
            class P:
                returncode = 0

                async def communicate(self):
                    return b"ok", b""

            return P()

        monkeypatch.setattr("asyncio.create_subprocess_exec", fake_exec)

        deployer = Deployer(session=session)
        dep = await deployer.deploy(repo.id)
        assert dep.status == "success"


@pytest.mark.asyncio
async def test_deploy_failure(tmp_path: Path, monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as session:
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        (repo_dir / "dummy.txt").write_text("x", encoding="utf-8")

        repo = Repository(
            project_id=1,
            name="repo",
            git_url="https://example.com/repo.git",
            branch="main",
            path="./",
            local_path=str(repo_dir),
            check_interval=60,
            last_commit_hash="abc",
        )
        session.add(repo)
        await session.flush()

        from Shiparr import git_manager

        async def fake_remote_hash(local_path, branch):  # type: ignore[unused-argument]
            return "def"

        async def fake_pull(local_path, branch="main"):  # type: ignore[unused-argument]
            return "def"

        git_manager.GitManager.get_remote_hash = fake_remote_hash  # type: ignore[assignment]
        git_manager.GitManager.pull = fake_pull  # type: ignore[assignment]

        async def fake_exec(*args, **kwargs):  # type: ignore[unused-argument]
            class P:
                returncode = 1

                async def communicate(self):
                    return b"", b"error"

            return P()

        monkeypatch.setattr("asyncio.create_subprocess_exec", fake_exec)

        deployer = Deployer(session=session)
        dep = await deployer.deploy(repo.id)
        assert dep.status == "failed"


@pytest.mark.asyncio
async def test_deploy_with_sops(tmp_path: Path, monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as session:
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        (repo_dir / "dummy.txt").write_text("x", encoding="utf-8")

        repo = Repository(
            project_id=1,
            name="repo",
            git_url="https://example.com/repo.git",
            branch="main",
            path="./",
            local_path=str(repo_dir),
            check_interval=60,
            last_commit_hash=None,
        )
        # Inject env_file attribute expected by Deployer
        repo.env_file = "file.env.enc"
        session.add(repo)
        await session.flush()

        from Shiparr import git_manager

        async def fake_pull(local_path, branch="main"):  # type: ignore[unused-argument]
            return "def"

        git_manager.GitManager.pull = fake_pull  # type: ignore[assignment]

        async def fake_dec(enc, out):  # type: ignore[unused-argument]
            return True

        # Patch SopsManager.decrypt_file uniquement pour ce test
        monkeypatch.setattr(
            "Shiparr.sops_manager.SopsManager.decrypt_file",
            fake_dec,
        )

        async def fake_exec(*args, **kwargs):  # type: ignore[unused-argument]
            class P:
                returncode = 0

                async def communicate(self):
                    return b"ok", b""

            return P()

        monkeypatch.setattr("asyncio.create_subprocess_exec", fake_exec)

        deployer = Deployer(session=session)
        dep = await deployer.deploy(repo.id)
        assert dep.status == "success"


@pytest.mark.asyncio
async def test_notifications_wiring(tmp_path: Path, monkeypatch):
    """Vérifie que NotificationManager récupère bien les URLs depuis la config.

    On mocke shoutrrr et on s'assure que les URLs du repo + global sont utilisées.
    """

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
            local_path=str(tmp_path / "repo"),
            check_interval=60,
            last_commit_hash=None,
        )
        session.add(repo)
        await session.flush()

        repo_cfg = RepositoryConfig(
            name="media-stack",
            url="https://example.com/repo.git",
            branch="main",
            path="./",
            local_path=str(tmp_path / "repo"),
            check_interval=60,
            notifications={
                "success": ["repo-success://url"],
                "failure": ["repo-failure://url"],
            },
        )
        project_cfg = ProjectConfig(
            project="homelab",
            description="",
            tokens=None,
            repositories={"media-stack": repo_cfg},
            global_notifications={
                "success": ["global-success://url"],
                "failure": ["global-failure://url"],
            },
        )
        loaded = LoadedConfig(settings=Settings(), projects={"homelab": project_cfg})

        sent_urls: list[str] = []

        async def fake_exec(*args, **kwargs):  # type: ignore[unused-argument]
            class P:
                async def communicate(self_inner):  # noqa: D401
                    # args: ("shoutrrr", "send", "-u", url, "-m", message)
                    url = args[3]
                    sent_urls.append(url)
                    return b"", b""

            return P()

        monkeypatch.setattr("asyncio.create_subprocess_exec", fake_exec)

        nm = NotificationManager(config=loaded, session_factory=async_session)

        dep = Deployment(
            repository_id=repo.id,
            commit_hash="abc",
            status="success",
            logs=None,
        )
        session.add(dep)
        await session.flush()

        await nm.notify_for_deployment("success", dep)

        # On doit avoir reçu repo-success et global-success
        assert "repo-success://url" in sent_urls
        assert "global-success://url" in sent_urls
