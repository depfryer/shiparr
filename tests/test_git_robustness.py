import pytest
from unittest.mock import MagicMock
from Shiparr.git_manager import GitManager, GitError
from git import GitCommandError

@pytest.mark.asyncio
async def test_pull_robustness(tmp_path, monkeypatch):
    # Mock Repo
    mock_repo = MagicMock()
    mock_origin = MagicMock()
    mock_repo.remotes.origin = mock_origin
    mock_repo.head.commit.hexsha = "abc"
    
    # Simulate fetch failure twice then success
    mock_origin.fetch.side_effect = [
        GitCommandError("fetch", "fail"),
        GitCommandError("fetch", "fail"),
        None
    ]
    
    def fake_Repo(path):
        return mock_repo
        
    monkeypatch.setattr("Shiparr.git_manager.Repo", fake_Repo)
    
    # Setup dir
    (tmp_path / "repo").mkdir()
    
    await GitManager.pull(tmp_path / "repo", branch="main")
    
    assert mock_origin.fetch.call_count == 3
    mock_repo.git.reset.assert_called_with("--hard", "origin/main")
    mock_repo.git.clean.assert_called_with("-fd")

@pytest.mark.asyncio
async def test_pull_failure(tmp_path, monkeypatch):
     # Mock Repo
    mock_repo = MagicMock()
    mock_origin = MagicMock()
    mock_repo.remotes.origin = mock_origin
    
    # Always fail
    mock_origin.fetch.side_effect = GitCommandError("fetch", "fail")
    
    def fake_Repo(path):
        return mock_repo
    monkeypatch.setattr("Shiparr.git_manager.Repo", fake_Repo)
    
    (tmp_path / "repo").mkdir()
    
    with pytest.raises(GitError):
        await GitManager.pull(tmp_path / "repo", branch="main")
