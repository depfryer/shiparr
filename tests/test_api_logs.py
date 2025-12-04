import pytest
import asyncio
from pathlib import Path
from quart import Quart
from Shiparr.app import create_app
from Shiparr.models import Repository, Project
from Shiparr import database

@pytest.mark.asyncio
async def test_get_repository_logs_stream(tmp_path, monkeypatch):
    # Setup Env
    monkeypatch.setenv("Shiparr_DATA_PATH", str(tmp_path))
    monkeypatch.setenv("Shiparr_CONFIG_PATH", str(tmp_path / "config"))
    
    app = create_app()
    app.config["TESTING"] = True
    # Disable Auth
    app.config["Shiparr_SETTINGS"].auth_enabled = False

    # Mock subprocess
    async def fake_exec(*args, **kwargs):
        assert "docker" in args
        assert "logs" in args
        
        class P:
            returncode = None
            class Stdout:
                async def readline(self):
                    await asyncio.sleep(0.01)
                    if not hasattr(self, "count"):
                        self.count = 0
                    self.count += 1
                    if self.count > 3:
                        return b""
                    return f"log line {self.count}\n".encode()
            
            stdout = Stdout()
            stderr = None
            
            def terminate(self):
                pass
            async def wait(self):
                pass
                
        return P()

    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_exec)

    async with app.test_app() as test_app:
        client = test_app.test_client()
        
        # Populate DB
        # Wait for startup to init DB
        assert database.async_session_factory is not None
        async with database.async_session_factory() as session:
             p = Project(name="p1", config_file="p1.yml")
             session.add(p)
             await session.flush()
             
             repo_dir = tmp_path / "repo"
             repo_dir.mkdir()
             
             repo = Repository(
                project_id=p.id,
                name="repo",
                git_url="http://u",
                branch="main",
                path="./",
                local_path=str(repo_dir),
                check_interval=60,
                healthcheck_timeout=60,
                healthcheck_expected_status=200,
                # Missing fields from model? No, I added healthcheck fields.
                # But wait, I added them in the previous step.
                # If test fails due to args, I know why.
             )
             session.add(repo)
             await session.flush()
             repo_id = repo.id
             await session.commit()

        resp = await client.get(f"/api/repositories/{repo_id}/logs?tail=10")
        assert resp.status_code == 200
        data = await resp.get_data()
        text = data.decode()
        assert "log line 1" in text
        assert "log line 3" in text
