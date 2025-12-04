"""Core REST API routes for Shiparr."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any

from quart import Blueprint, Response, current_app, jsonify, request
from sqlalchemy import select

from ..auth import require_basic_auth
from ..database import get_session
from ..deployer import Deployer
from ..models import Deployment, Project, Repository


def register(bp: Blueprint) -> None:
    bp.add_url_rule("/api/health", view_func=health, methods=["GET"])
    bp.add_url_rule("/api/projects", view_func=list_projects, methods=["GET"])
    bp.add_url_rule("/api/projects/<string:name>", view_func=get_project, methods=["GET"])
    bp.add_url_rule(
        "/api/projects/<string:name>/repositories",
        view_func=list_project_repositories,
        methods=["GET"],
    )
    bp.add_url_rule(
        "/api/repositories/<int:repo_id>",
        view_func=get_repository,
        methods=["GET"],
    )
    bp.add_url_rule(
        "/api/repositories/<int:repo_id>/deployments",
        view_func=list_deployments,
        methods=["GET"],
    )
    bp.add_url_rule(
        "/api/repositories/<int:repo_id>/deploy",
        view_func=trigger_deploy,
        methods=["POST"],
    )
    bp.add_url_rule(
        "/api/deployments/<int:deployment_id>",
        view_func=get_deployment,
        methods=["GET"],
    )
    bp.add_url_rule(
        "/api/deployments/<int:deployment_id>/logs",
        view_func=get_deployment_logs,
        methods=["GET"],
    )
    bp.add_url_rule(
        "/api/repositories/<int:repo_id>/logs",
        view_func=get_repository_logs,
        methods=["GET"],
    )


async def health() -> Any:
    return jsonify({"status": "ok"})


@require_basic_auth
async def list_projects() -> Any:
    async for session in get_session():
        stmt = select(Project)
        result = await session.execute(stmt)
        projects = [
            {"id": p.id, "name": p.name, "config_file": p.config_file, "created_at": p.created_at.isoformat()}
            for p in result.scalars().all()
        ]
        return jsonify(projects)


@require_basic_auth
async def get_project(name: str) -> Any:
    async for session in get_session():
        stmt = select(Project).where(Project.name == name)
        result = await session.execute(stmt)
        project = result.scalar_one_or_none()
        if project is None:
            return jsonify({"error": "not_found"}), 404

        # Récupérer les repositories et leur dernier déploiement
        stmt = select(Repository).where(Repository.project_id == project.id)
        result = await session.execute(stmt)
        repositories = result.scalars().all()

        repos_data = []
        for repo in repositories:
            # Dernier déploiement
            stmt = (
                select(Deployment)
                .where(Deployment.repository_id == repo.id)
                .order_by(Deployment.id.desc())
                .limit(1)
            )
            deployment_result = await session.execute(stmt)
            last_deployment = deployment_result.scalar_one_or_none()

            repo_data = {
                "id": repo.id,
                "name": repo.name,
                "git_url": repo.git_url,
                "branch": repo.branch,
                "status": last_deployment.status if last_deployment else "never_deployed",
                "last_check": repo.last_commit_hash,  # Ou autre indicateur
            }
            
            if last_deployment:
                repo_data["last_deployment"] = {
                    "id": last_deployment.id,
                    "status": last_deployment.status,
                    "finished_at": last_deployment.finished_at.isoformat() if last_deployment.finished_at else None,
                    "logs_url": f"/api/deployments/{last_deployment.id}/logs"
                }
            
            repos_data.append(repo_data)

        return jsonify(
            {
                "id": project.id,
                "name": project.name,
                "config_file": project.config_file,
                "created_at": project.created_at.isoformat(),
                "repositories": repos_data
            }
        )


@require_basic_auth
async def list_project_repositories(name: str) -> Any:
    async for session in get_session():
        stmt = select(Project).where(Project.name == name)
        result = await session.execute(stmt)
        project = result.scalar_one_or_none()
        if project is None:
            return jsonify({"error": "not_found"}), 404

        stmt = select(Repository).where(Repository.project_id == project.id)
        result = await session.execute(stmt)
        repos = [
            {
                "id": r.id,
                "name": r.name,
                "git_url": r.git_url,
                "branch": r.branch,
                "local_path": r.local_path,
            }
            for r in result.scalars().all()
        ]
        return jsonify(repos)


@require_basic_auth
async def get_repository(repo_id: int) -> Any:
    async for session in get_session():
        stmt = select(Repository).where(Repository.id == repo_id)
        result = await session.execute(stmt)
        repo = result.scalar_one_or_none()
        if repo is None:
            return jsonify({"error": "not_found"}), 404
        return jsonify(
            {
                "id": repo.id,
                "name": repo.name,
                "git_url": repo.git_url,
                "branch": repo.branch,
                "path": repo.path,
                "local_path": repo.local_path,
                "check_interval": repo.check_interval,
            }
        )


@require_basic_auth
async def list_deployments(repo_id: int) -> Any:
    async for session in get_session():
        stmt = select(Deployment).where(Deployment.repository_id == repo_id)
        result = await session.execute(stmt)
        deployments = [
            {
                "id": d.id,
                "status": d.status,
                "commit_hash": d.commit_hash,
                "started_at": d.started_at.isoformat() if d.started_at else None,
                "finished_at": d.finished_at.isoformat() if d.finished_at else None,
            }
            for d in result.scalars().all()
        ]
        return jsonify(deployments)


@require_basic_auth
async def trigger_deploy(repo_id: int) -> Any:
    queue = current_app.config.get("Shiparr_QUEUE")
    if queue:
        await queue.enqueue(repo_id, priority=100)
        return jsonify({"status": "queued", "message": "Deployment enqueued"})

    async for session in get_session():
        notifications = current_app.config.get("Shiparr_NOTIFICATIONS")
        settings = current_app.config["Shiparr_SETTINGS"]
        deployer = Deployer(
            session=session, 
            notifications=notifications,
            prune_enabled=settings.enable_image_prune
        )
        deployment = await deployer.deploy(repo_id)
        return jsonify({"deployment_id": deployment.id, "status": deployment.status})


@require_basic_auth
async def get_deployment(deployment_id: int) -> Any:
    async for session in get_session():
        stmt = select(Deployment).where(Deployment.id == deployment_id)
        result = await session.execute(stmt)
        deployment = result.scalar_one_or_none()
        if deployment is None:
            return jsonify({"error": "not_found"}), 404
        return jsonify(
            {
                "id": deployment.id,
                "repository_id": deployment.repository_id,
                "status": deployment.status,
                "commit_hash": deployment.commit_hash,
                "started_at": deployment.started_at.isoformat() if deployment.started_at else None,
                "finished_at": deployment.finished_at.isoformat() if deployment.finished_at else None,
            }
        )


@require_basic_auth
async def get_deployment_logs(deployment_id: int) -> Any:
    async for session in get_session():
        stmt = select(Deployment).where(Deployment.id == deployment_id)
        result = await session.execute(stmt)
        deployment = result.scalar_one_or_none()
        if deployment is None:
            return jsonify({"error": "not_found"}), 404
        return jsonify({"logs": deployment.logs or ""})


@require_basic_auth
async def get_repository_logs(repo_id: int) -> Any:
    """Stream logs using docker compose logs -fn."""
    async for session in get_session():
        stmt = select(Repository).where(Repository.id == repo_id)
        result = await session.execute(stmt)
        repo = result.scalar_one_or_none()
        if repo is None:
            return jsonify({"error": "not_found"}), 404
        
        tail = request.args.get("tail", default=100, type=int)
        
        local_path = Path(repo.local_path).resolve()
        if repo.path:
             workdir = local_path / repo.path
        else:
             workdir = local_path
             
        if not workdir.exists():
            return jsonify({"error": "workdir_not_found"}), 404

        env = {**os.environ, "COMPOSE_PROJECT_NAME": f"shiparr_repo_{repo.id}"}
        cmd = ["docker", "compose", "logs", "-f", "-n", str(tail)]

        async def generate(cmd=cmd, workdir=workdir, env=env):
            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(workdir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                env=env
            )
            
            try:
                while True:
                    line = await process.stdout.readline()
                    if not line:
                        break
                    yield line
            except asyncio.CancelledError:
                if process.returncode is None:
                    process.terminate()
                    try:
                        await process.wait()
                    except Exception:
                        pass
                raise

        return Response(generate(), mimetype="text/plain")
