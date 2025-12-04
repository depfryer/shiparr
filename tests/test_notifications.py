from __future__ import annotations

import asyncio

import pytest

from Shiparr.models import Deployment
from Shiparr.notifications import NotificationManager


@pytest.mark.asyncio
async def test_notify_success(monkeypatch):
    async def fake_exec(*args, **kwargs):  # type: ignore[unused-argument]
        class P:
            async def communicate(self):
                return b"", b""

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
    nm = NotificationManager()
    await nm.notify(["dummy://url"], "success", dep)


@pytest.mark.asyncio
async def test_notify_failure_silent(monkeypatch):
    async def fake_exec(*args, **kwargs):  # type: ignore[unused-argument]
        class P:
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
    nm = NotificationManager()
    await nm.notify(["dummy://url"], "failure", dep)


def test_format_message():
    dep = Deployment(
        id=1,
        repository_id=1,
        commit_hash="abc",
        status="success",
        started_at=None,
        finished_at=None,
        logs=None,
    )
    nm = NotificationManager()
    msg = nm.format_message("success", dep)
    assert "Shiparr" in msg
    assert "deployment_id=1" in msg
