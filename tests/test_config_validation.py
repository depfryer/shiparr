from pathlib import Path

import pytest

from Shiparr.config import ConfigLoader, Settings


def test_valid_config(tmp_path: Path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "valid.yaml").write_text("""
project: valid
repositories:
  repo1:
    url: http://git
    local_path: /tmp/repo1
""", encoding="utf-8")
    
    settings = Settings(config_path=config_dir)
    loader = ConfigLoader(settings)
    loaded = loader.load()
    assert "valid" in loaded.projects

def test_invalid_extra_field(tmp_path: Path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "invalid.yaml").write_text("""
project: invalid
extra_field: value
repositories:
  repo1:
    url: http://git
    local_path: /tmp/repo1
""", encoding="utf-8")
    
    settings = Settings(config_path=config_dir)
    loader = ConfigLoader(settings)
    with pytest.raises(ValueError) as exc:
        loader.load()
    # Pydantic V2 error message for extra fields
    assert "Extra inputs are not permitted" in str(exc.value)

def test_invalid_repo_extra_field(tmp_path: Path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "invalid_repo.yaml").write_text("""
project: invalid_repo
repositories:
  repo1:
    url: http://git
    local_path: /tmp/repo1
    unknown_option: yes
""", encoding="utf-8")
    
    settings = Settings(config_path=config_dir)
    loader = ConfigLoader(settings)
    with pytest.raises(ValueError) as exc:
        loader.load()
    assert "Extra inputs are not permitted" in str(exc.value)
