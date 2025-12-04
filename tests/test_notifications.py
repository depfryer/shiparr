from __future__ import annotations

import pytest

from Shiparr.config import LoadedConfig, Settings
from Shiparr.models import Deployment
from Shiparr.notifications import NotificationManager


def _make_nm() -> NotificationManager:
    """Build a NotificationManager with a dummy config/session for unit tests.

    For these tests we exercise `notify` and `format_message` only, so
    `session_factory` is never used and can safely be `None`.
    """

    cfg = LoadedConfig(settings=Settings(), projects={})
    return NotificationManager(config=cfg, session_factory=None)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_notify_success(monkeypatch):
    async def fake_exec(*args, **kwargs):  # type: ignore[unused-argument]
        class P:
            returncode = 0

            async def communicate(self):
                return b"ok", b""

        return P()

    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_exec)

    dep = Deployment(
        id=1,
        repository_id=1,
        commit_hash="abc",
        status="success",
        started_at=None,
        finished_at=None,
        logs=None,
    )
    nm = _make_nm()
    await nm.notify(["dummy://url"], "success", dep)


@pytest.mark.asyncio
async def test_notify_failure_silent(monkeypatch):
    async def fake_exec(*args, **kwargs):  # type: ignore[unused-argument]
        class P:
            returncode = 1

            async def communicate(self):
                return b"", b"error"

        return P()

    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_exec)

    dep = Deployment(
        id=1,
        repository_id=1,
        commit_hash="abc",
        status="failed",
        started_at=None,
        finished_at=None,
        logs=None,
    )
    nm = _make_nm()
    # Doit logger l'erreur mais ne pas lever d'exception
    await nm.notify(["dummy://url"], "failure", dep)


@pytest.mark.asyncio
async def test_notify_shoutrrr_missing(monkeypatch):
    async def fake_exec(*args, **kwargs):  # type: ignore[unused-argument]
        raise FileNotFoundError("shoutrrr not found")

    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_exec)

    dep = Deployment(
        id=1,
        repository_id=1,
        commit_hash="abc",
        status="success",
        started_at=None,
        finished_at=None,
        logs=None,
    )
    nm = _make_nm()
    # L'absence de binaire ne doit pas remonter une exception utilisateur
    await nm.notify(["dummy://url"], "success", dep)


def test_format_message_contains_fields():
    dep = Deployment(
        id=42,
        repository_id=7,
        commit_hash="abc",
        status="success",
        started_at=None,
        finished_at=None,
        logs=None,
    )
    nm = _make_nm()
    msg = nm.format_message("success", dep)
    assert "Shiparr" in msg
    assert "deployment_id=42" in msg
    assert "repo=7" in msg
