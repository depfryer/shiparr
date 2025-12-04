from __future__ import annotations

import os
from pathlib import Path

from Shiparr.config import ConfigLoader, Settings, _load_yaml_file


def test_load_valid_yaml(tmp_path: Path) -> None:
    path = tmp_path / "valid.yaml"
    path.write_text("project: homelab\nrepositories: {}\n", encoding="utf-8")
    data = _load_yaml_file(path)
    assert data["project"] == "homelab"


def test_load_invalid_yaml(tmp_path: Path) -> None:
    path = tmp_path / "invalid.yaml"
    path.write_text("- just: a list\n- not: a mapping\n", encoding="utf-8")
    try:
        _load_yaml_file(path)
    except ValueError:
        pass
    else:
        assert False, "Expected ValueError for non-mapping root"


def test_env_variable_resolution(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "abc123")
    path = tmp_path / "env.yaml"
    path.write_text("token: ${GITHUB_TOKEN}\n", encoding="utf-8")
    data = _load_yaml_file(path)
    assert data["token"] == "abc123"


def test_missing_required_fields(tmp_path: Path) -> None:
    # repositories manquant
    path = tmp_path / "bad.yaml"
    path.write_text("project: homelab\n", encoding="utf-8")
    settings = Settings(config_path=tmp_path)
    loader = ConfigLoader(settings=settings)
    try:
        loader.load()
    except Exception:
        pass
    else:
        assert False, "Expected validation error when repositories missing"


def test_multiple_repositories(tmp_path: Path) -> None:
    path = tmp_path / "multi.yaml"
    path.write_text(
        """project: homelab
repositories:
  repo1:
    url: https://example.com/repo1.git
    local_path: /tmp/repo1
  repo2:
    url: https://example.com/repo2.git
    local_path: /tmp/repo2
""",
        encoding="utf-8",
    )
    settings = Settings(config_path=tmp_path)
    loader = ConfigLoader(settings=settings)
    loaded = loader.load()
    assert "homelab" in loaded.projects
    project = loaded.projects["homelab"]
    assert set(project.repositories.keys()) == {"repo1", "repo2"}
