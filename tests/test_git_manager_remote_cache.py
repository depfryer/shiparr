from __future__ import annotations

from pathlib import Path

import importlib

import pytest

from git import GitCommandError
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


@pytest.mark.asyncio
async def test_get_remote_hash_refetches_after_ttl(monkeypatch, tmp_path: Path) -> None:
    importlib.reload(gm)

    path = tmp_path / "repo_ttl"
    path.mkdir()
    (path / ".git").mkdir()

    calls = {"fetch": 0}

    class DummyOrigin:
        def fetch(self):
            calls["fetch"] += 1

        class Refs:
            def __getitem__(self, item):
                class Ref:
                    class Commit:
                        hexsha = "new_hash"

                    commit = Commit()

                return Ref()

        refs = Refs()

    class DummyRepo:
        remotes = type("R", (), {"origin": DummyOrigin()})()

    def fake_repo(local_path):
        return DummyRepo()

    monkeypatch.setattr(gm, "Repo", fake_repo)

    # Mock time to control TTL logic
    mock_time = 1000.0
    monkeypatch.setattr(gm.time, "monotonic", lambda: mock_time)

    # Prime the cache with an expired entry
    # TTL is 5.0s, so if we set timestamp to (mock_time - TTL - 1), it is expired.
    cache_key = (str(path.resolve()), "main")
    expired_ts = mock_time - gm._REMOTE_HASH_TTL_SECONDS - 1.0
    gm._REMOTE_HASH_CACHE[cache_key] = (expired_ts, "old_hash")

    # Call get_remote_hash
    h = await gm.GitManager.get_remote_hash(path, "main")

    # It should have fetched new hash
    assert h == "new_hash"
    assert calls["fetch"] == 1

    # Cache should be updated
    assert gm._REMOTE_HASH_CACHE[cache_key][1] == "new_hash"
    assert gm._REMOTE_HASH_CACHE[cache_key][0] == mock_time


@pytest.mark.asyncio
async def test_get_remote_hash_raises_giterror_on_failure_no_cache(
    monkeypatch, tmp_path: Path
) -> None:
    importlib.reload(gm)
    path = tmp_path / "repo_error"
    path.mkdir()

    def fake_repo_fail(local_path):
        raise GitCommandError("fetch", "failed")

    monkeypatch.setattr(gm, "Repo", fake_repo_fail)

    # Ensure cache is empty
    gm._REMOTE_HASH_CACHE.clear()

    # Use gm.GitError because reload(gm) created a new class
    with pytest.raises(gm.GitError) as exc:
        await gm.GitManager.get_remote_hash(path, "main")

    assert "failed" in str(exc.value)
