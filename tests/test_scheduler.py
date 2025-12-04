from __future__ import annotations

from types import SimpleNamespace

import pytest

from Shiparr.scheduler import DeploymentScheduler


@pytest.mark.asyncio
async def test_schedule_and_reschedule_repository() -> None:
    called: list[int] = []

    async def dummy_deploy(repo_id: int) -> None:
        called.append(repo_id)

    scheduler = DeploymentScheduler(deploy_callable=dummy_deploy)
    scheduler.start()
    try:
        repo = SimpleNamespace(id=1, name="repo1", check_interval=5)

        scheduler.schedule_repository(repo)
        job = scheduler.scheduler.get_job("repo_repo1")
        assert job is not None
        # APScheduler stores args as a tuple
        assert job.args == (1,)
        assert job.trigger.interval.total_seconds() == 5

        # Change interval and ensure job is updated
        repo.check_interval = 10
        scheduler.schedule_repository(repo)
        job2 = scheduler.scheduler.get_job("repo_repo1")
        assert job2 is not None
        assert job2.trigger.interval.total_seconds() == 10

        # reschedule_all should keep jobs consistent
        repo2 = SimpleNamespace(id=2, name="repo2", check_interval=7)
        scheduler.reschedule_all([repo, repo2])
        job_repo2 = scheduler.scheduler.get_job("repo_repo2")
        assert job_repo2 is not None
        assert job_repo2.args == (2,)

    finally:
        scheduler.stop()
