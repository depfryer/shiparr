from __future__ import annotations

from pathlib import Path

import pytest

from Shiparr.git_manager import GitManager


@pytest.mark.asyncio
async def test_clone_public_repo(monkeypatch, tmp_path: Path):
    class DummyRepo:
        class Head:
            commit = type("C", (), {"hexsha": "abc"})

        head = Head()

    def fake_clone_from(url, path, branch=None):  # type: ignore[unused-argument]
        return DummyRepo()

    monkeypatch.setattr("Shiparr.git_manager.Repo.clone_from", fake_clone_from)
    h = await GitManager.clone("https://example.com/repo.git", "main", tmp_path / "repo")
    assert h == "abc"


@pytest.mark.asyncio
async def test_get_local_hash(monkeypatch, tmp_path: Path):
    class DummyRepo:
        class Head:
            commit = type("C", (), {"hexsha": "def"})

        head = Head()

    def fake_repo(path):  # type: ignore[unused-argument]
        return DummyRepo()

    (tmp_path / ".git").mkdir()
    monkeypatch.setattr("Shiparr.git_manager.Repo", fake_repo)
    h = await GitManager.get_local_hash(tmp_path)
    assert h == "def"


@pytest.mark.asyncio
async def test_has_changes_true(monkeypatch, tmp_path: Path):
    async def fake_local(path):  # type: ignore[unused-argument]
        return "111"

    async def fake_remote(path, branch, url=None, token=None):  # type: ignore[unused-argument]
        return "222"

    monkeypatch.setattr("Shiparr.git_manager.GitManager.get_local_hash", fake_local)
    monkeypatch.setattr("Shiparr.git_manager.GitManager.get_remote_hash", fake_remote)

    assert await GitManager.has_changes(tmp_path, "main") is True


@pytest.mark.asyncio
async def test_has_changes_false(monkeypatch, tmp_path: Path):
    async def fake_local(path):  # type: ignore[unused-argument]
        return "111"

    async def fake_remote(path, branch, url=None, token=None):  # type: ignore[unused-argument]
        return "111"

    monkeypatch.setattr("Shiparr.git_manager.GitManager.get_local_hash", fake_local)
    monkeypatch.setattr("Shiparr.git_manager.GitManager.get_remote_hash", fake_remote)

    assert await GitManager.has_changes(tmp_path, "main") is False


@pytest.mark.asyncio
async def test_pull_success(monkeypatch, tmp_path: Path):
    class DummyOrigin:
        def pull(self):
            return None

    class DummyRepo:
        remotes = type("R", (), {"origin": DummyOrigin()})()
        head = type("H", (), {"commit": type("C", (), {"hexsha": "def"})()})()

    def fake_repo(path):  # type: ignore[unused-argument]
        return DummyRepo()

    (tmp_path / ".git").mkdir()
    monkeypatch.setattr("Shiparr.git_manager.Repo", fake_repo)

    h = await GitManager.pull(tmp_path)
    assert h == "def"
