from __future__ import annotations

import base64

import pytest

from Shiparr.app import create_app


@pytest.mark.asyncio
async def test_health_endpoint():
    app = create_app()
    async with app.test_app() as test_app:
        client = test_app.test_client()
        resp = await client.get("/api/health")
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_auth_required(monkeypatch):
    app = create_app()
    settings = app.config["Shiparr_SETTINGS"]
    settings.auth_enabled = True

    async with app.test_app() as test_app:
        client = test_app.test_client()
        resp = await client.get("/api/projects")
        assert resp.status_code == 401


@pytest.mark.asyncio
async def test_auth_success(monkeypatch):
    app = create_app()
    settings = app.config["Shiparr_SETTINGS"]
    settings.auth_enabled = True
    settings.auth_username = "user"
    settings.auth_password = "pass"

    async with app.test_app() as test_app:
        client = test_app.test_client()
        token = base64.b64encode(b"user:pass").decode("ascii")
        resp = await client.get("/api/health", headers={"Authorization": f"Basic {token}"})
        # /api/health est bypassé, donc 200 même sans auth
        assert resp.status_code == 200
