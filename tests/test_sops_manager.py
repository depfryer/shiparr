from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from Shiparr.sops_manager import SopsError, SopsManager


@pytest.mark.asyncio
async def test_decrypt_success(monkeypatch, tmp_path: Path):
    async def fake_exec(*args, **kwargs):  # type: ignore[unused-argument]
        class P:
            returncode = 0

            async def communicate(self):
                return b"KEY=VALUE", b""

        return P()

    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_exec)
    enc = tmp_path / "file.env.enc"
    enc.write_text("dummy", encoding="utf-8")
    out = tmp_path / "file.env"
    ok = await SopsManager.decrypt_file(enc, out)
    assert ok is True
    assert out.read_text(encoding="utf-8") == "KEY=VALUE"


@pytest.mark.asyncio
async def test_decrypt_failure(monkeypatch, tmp_path: Path):
    async def fake_exec(*args, **kwargs):  # type: ignore[unused-argument]
        class P:
            returncode = 1

            async def communicate(self):
                return b"", b"error"

        return P()

    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_exec)
    enc = tmp_path / "file.env.enc"
    enc.write_text("dummy", encoding="utf-8")
    out = tmp_path / "file.env"
    with pytest.raises(SopsError):
        await SopsManager.decrypt_file(enc, out)


def test_is_sops_file_true(tmp_path: Path):
    p = tmp_path / "sops.yaml"
    p.write_text("sops:\n  foo: bar\n", encoding="utf-8")
    assert asyncio.run(SopsManager.is_sops_file(p)) is True


def test_is_sops_file_false(tmp_path: Path):
    p = tmp_path / "plain.yaml"
    p.write_text("key: value\n", encoding="utf-8")
    assert asyncio.run(SopsManager.is_sops_file(p)) is False
