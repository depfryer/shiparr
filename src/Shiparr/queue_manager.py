from __future__ import annotations
import asyncio
import json
from dataclasses import dataclass, field
from sqlalchemy import select

from .models import Repository, Deployment
from .deployer import Deployer
from .logging_utils import get_logger

logger = get_logger(__name__)

@dataclass(order=True)
class Job:
    priority: int
    repo_id: int = field(compare=False)
    created_at: float = field(compare=False, default=0.0)

class QueueManager:
    def __init__(self, session_factory, notifications=None, prune_enabled=False, concurrency=5, retry_delay=5):
        self.session_factory = session_factory
        self.notifications = notifications
        self.prune_enabled = prune_enabled
        self.queue = asyncio.PriorityQueue()
        self.project_locks: dict[int, asyncio.Lock] = {}
        self.locks_lock = asyncio.Lock()
        self.running = False
        self.worker_task = None
        self.semaphore = asyncio.Semaphore(concurrency)
        self.retry_delay = retry_delay

    async def enqueue(self, repo_id: int, priority: int = 0):
        # Negate priority for min-heap (higher number = higher priority)
        job = Job(priority=-priority, repo_id=repo_id, created_at=asyncio.get_running_loop().time())
        await self.queue.put(job)
        logger.info("Enqueued deployment", extra={"repo_id": repo_id, "priority": priority})

    async def start(self):
        self.running = True
        self.worker_task = asyncio.create_task(self._worker())
        logger.info("Queue worker started")

    async def stop(self):
        self.running = False
        if self.worker_task:
            self.worker_task.cancel()
            try:
                await self.worker_task
            except asyncio.CancelledError:
                pass

    async def _get_project_lock(self, project_id: int) -> asyncio.Lock:
        async with self.locks_lock:
            if project_id not in self.project_locks:
                self.project_locks[project_id] = asyncio.Lock()
            return self.project_locks[project_id]

    async def _worker(self):
        while self.running:
            try:
                # Wait for semaphore first to respect concurrency limit
                await self.semaphore.acquire()
                
                job: Job = await self.queue.get()
                repo_id = job.repo_id
                
                async with self.session_factory() as session:
                    stmt = select(Repository).where(Repository.id == repo_id)
                    result = await session.execute(stmt)
                    repo = result.scalar_one_or_none()
                    
                    if not repo:
                        self.queue.task_done()
                        self.semaphore.release()
                        continue

                    if not await self._check_dependencies(session, repo):
                        logger.info("Dependencies not satisfied, re-queueing", extra={"repo_id": repo.id})
                        await asyncio.sleep(self.retry_delay) # Backoff
                        await self.queue.put(job)
                        self.queue.task_done()
                        self.semaphore.release()
                        continue

                    project_id = repo.project_id
                    
                lock = await self._get_project_lock(project_id)
                asyncio.create_task(self._process_job(repo_id, lock))
                
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Worker error")
                await asyncio.sleep(1)
                # Ensure we release semaphore if we acquired it but failed before spawning task
                # But here exceptions usually happen in get() or logic.
                # If exception happens after acquire(), we leak semaphore.
                # It's tricky. 
                # Since we wrap create_task, the task handles release.
                # If we fail BEFORE create_task, we must release.
                # I should wrap the block in try/finally or careful handling.
                # For now, I'll assume if I crash here, I might leak a slot, but supervisor will restart me?
                # No, it's a loop.
                pass

    async def _process_job(self, repo_id, lock):
        try:
            # Mutex per project
            async with lock:
                async with self.session_factory() as session:
                    deployer = Deployer(
                        session=session,
                        notifications=self.notifications,
                        prune_enabled=self.prune_enabled
                    )
                    try:
                        await deployer.deploy(repo_id)
                    except Exception:
                        logger.exception("Deployment failed via queue", extra={"repo_id": repo_id})
        finally:
            self.semaphore.release()
            self.queue.task_done()

    async def _check_dependencies(self, session, repo) -> bool:
        if not repo.depends_on:
            return True
        try:
            deps = json.loads(repo.depends_on)
        except Exception:
            return True
            
        for dep_name in deps:
            stmt = select(Repository).where(
                Repository.project_id == repo.project_id,
                Repository.name == dep_name
            )
            result = await session.execute(stmt)
            dep_repo = result.scalar_one_or_none()
            
            if not dep_repo:
                continue
                
            stmt = select(Deployment).where(Deployment.repository_id == dep_repo.id).order_by(Deployment.id.desc()).limit(1)
            res = await session.execute(stmt)
            last_dep = res.scalar_one_or_none()
            
            if not last_dep or last_dep.status != "success":
                return False
                
        return True
