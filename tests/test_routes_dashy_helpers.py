from __future__ import annotations

from types import SimpleNamespace

import pytest

from Shiparr.routes.dashy import _status_class, _container_ok, _get_repo_containers


def test_status_class_mapping() -> None:
    assert _status_class("success") == "status-success"
    assert _status_class("running") == "status-running"
    assert _status_class("failed") == "status-failed"
    assert _status_class("unknown") == "status-unknown"
    # Fallback
    assert _status_class("something") == "status-unknown"


def test_container_ok_with_health() -> None:
    container = SimpleNamespace(
        attrs={
            "State": {
                "Health": {"Status": "healthy"},
                "Status": "running",
            }
        },
        status="exited",
    )
    assert _container_ok(container) is True


def test_container_ok_with_status_only() -> None:
    container = SimpleNamespace(
        attrs={"State": {"Status": "running"}},
        status="running",
    )
    assert _container_ok(container) is True


def test_container_not_ok_on_exception() -> None:
    class Broken:
        def __getattr__(self, name):  # pragma: no cover - defensive
            raise RuntimeError("boom")

    assert _container_ok(Broken()) is False


def test_get_repo_containers_handles_no_docker(monkeypatch) -> None:
    # Force helper to act as if Docker is unavailable
    monkeypatch.setattr("Shiparr.routes.dashy._get_docker_client", lambda: None)
    assert _get_repo_containers(1) == []


def test_get_repo_containers_handles_api_error(monkeypatch) -> None:
    from Shiparr.routes import dashy as dashy_mod

    class DummyContainers:
        def list(self, **kwargs):  # type: ignore[unused-argument]
            # Raise the specific APIError type that _get_repo_containers catches
            raise dashy_mod.docker.errors.APIError("API error", None, None)

    class DummyClient:
        containers = DummyContainers()

    monkeypatch.setattr("Shiparr.routes.dashy._get_docker_client", lambda: DummyClient())
    # Should swallow the error and return []
    assert _get_repo_containers(1) == []
