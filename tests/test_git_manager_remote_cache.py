from __future__ import annotations

from pathlib import Path

import importlib

import pytest

import Shiparr.git_manager as gm
from Shiparr.git_manager import GitError


@pytest.mark.asyncio
async def test_get_remote_hash_uses_cache(monkeypatch, tmp_path: Path) -> None:
    # Reload module to restore original GitManager.get_remote_hash implementation
    importlib.reload(gm)

    path = tmp_path / "repo"
    path.mkdir()
    (path / ".git").mkdir()

    calls = {"fetch": 0}

    class DummyOrigin:
        def fetch(self):
            calls["fetch"] += 1

        class Refs:
            def __getitem__(self, item):  # type: ignore[unused-argument]
                class Ref:
                    class Commit:
                        hexsha = "abc"

                    commit = Commit()

                return Ref()

        refs = Refs()

    class DummyRepo:
        remotes = type("R", (), {"origin": DummyOrigin()})()

    def fake_repo(local_path):  # type: ignore[unused-argument]
        return DummyRepo()

    monkeypatch.setattr(gm, "Repo", fake_repo)

    # First call should perform a fetch
    h1 = await gm.GitManager.get_remote_hash(path, "main")
    assert h1 == "abc"
    assert calls["fetch"] == 1

    # Second call with same path/branch should use cache (no new fetch)
    h2 = await gm.GitManager.get_remote_hash(path, "main")
    assert h2 == "abc"
    assert calls["fetch"] == 1
