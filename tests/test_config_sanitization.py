import pytest
from pydantic import ValidationError

from Shiparr.config import ProjectConfig, RepositoryConfig


def test_valid_names():
    RepositoryConfig(name="valid-name_1", url="u", local_path="/tmp")
    ProjectConfig(project="valid-project_1", repositories={})

def test_invalid_repo_name():
    with pytest.raises(ValidationError) as exc:
        RepositoryConfig(name="invalid name", url="u", local_path="/tmp")
    assert "alphanumeric" in str(exc.value)

    with pytest.raises(ValidationError) as exc:
        RepositoryConfig(name="invalid/name", url="u", local_path="/tmp")
    assert "alphanumeric" in str(exc.value)

def test_invalid_project_name():
    with pytest.raises(ValidationError) as exc:
        ProjectConfig(project="invalid name", repositories={})
    assert "alphanumeric" in str(exc.value)
