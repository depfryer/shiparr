import pytest
from pydantic import ValidationError
from Shiparr.config import RepositoryConfig

def test_valid_path():
    cfg = RepositoryConfig(
        name="repo", url="u", local_path="/tmp", path="./src"
    )
    assert cfg.path == "./src"

def test_path_traversal():
    with pytest.raises(ValidationError) as exc:
        RepositoryConfig(
            name="repo", url="u", local_path="/tmp", path="../src"
        )
    assert "Invalid path" in str(exc.value)

def test_absolute_path():
    with pytest.raises(ValidationError) as exc:
        RepositoryConfig(
            name="repo", url="u", local_path="/tmp", path="/etc"
        )
    assert "doit être relatif" in str(exc.value)

def test_deep_traversal():
    with pytest.raises(ValidationError) as exc:
        RepositoryConfig(
            name="repo", url="u", local_path="/tmp", path="foo/../../bar"
        )
    # foo/../../bar -> /dummy_root/foo/../../bar -> /dummy_root/../bar -> /bar (not in /dummy_root)
    assert "Invalid path" in str(exc.value)

def test_allowed_deep_path():
    cfg = RepositoryConfig(
        name="repo", url="u", local_path="/tmp", path="foo/bar/baz"
    )
    assert cfg.path == "foo/bar/baz"
