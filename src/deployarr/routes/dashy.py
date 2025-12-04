"""Dashy widget endpoint."""

from __future__ import annotations

import html as html_lib
from typing import Any

import docker
from quart import Blueprint, Response, jsonify, request
from sqlalchemy import select

from ..auth import require_basic_auth
from ..database import get_session
from ..models import Deployment, Project, Repository


def register(bp: Blueprint) -> None:
    # Ancien endpoint JSON pour widget Dashy "custom" (toujours supporté)
    bp.add_url_rule("/widget/dashy", view_func=dashy_widget, methods=["GET"])
    # Ancienne vue HTML basée sur ?project=, maintenant un simple alias vers /widget/projects/<name>
    bp.add_url_rule("/widget/dashy/html", view_func=dashy_widget_html, methods=["GET"])

    # Nouveaux widgets de navigation par projet / dépôt
    bp.add_url_rule("/widget/projects", view_func=projects_overview_html, methods=["GET"])
    bp.add_url_rule(
        "/widget/projects/<string:project_name>",
        view_func=project_overview_html,
        methods=["GET"],
    )
    bp.add_url_rule(
        "/widget/projects/<int:repo_id>/containers",
        view_func=repo_containers_html,
        methods=["GET"],
    )
    bp.add_url_rule(
        "/widget/projects/<int:repo_id>/containers/logs",
        view_func=repo_container_logs_html,
        methods=["GET"],
    )


@require_basic_auth
async def dashy_widget() -> Any:
    project_name = request.args.get("project")
    if not project_name:
        return jsonify({"error": "missing_project"}), 400

    async for session in get_session():
        stmt = select(Project).where(Project.name == project_name)
        result = await session.execute(stmt)
        project = result.scalar_one_or_none()
        if project is None:
            return jsonify({"error": "not_found"}), 404

        stmt = select(Repository).where(Repository.project_id == project.id)
        result = await session.execute(stmt)
        repos = result.scalars().all()

        widgets: list[dict[str, Any]] = []

        for repo in repos:
            # Récupérer le dernier déploiement pour ce repo
            stmt = (
                select(Deployment)
                .where(Deployment.repository_id == repo.id)
                .order_by(Deployment.started_at.desc())
                .limit(1)
            )
            result = await session.execute(stmt)
            deployment = result.scalar_one_or_none()

            status = "unknown"
            last_hash = ""
            last_deploy = None
            if deployment:
                status = deployment.status
                last_hash = deployment.commit_hash
                last_deploy = deployment.started_at

            widgets.extend(
                [
                    {
                        "type": "text",
                        "value": repo.name,
                        "label": "Repository",
                    },
                    {
                        "type": "text",
                        "value": last_hash,
                        "label": "Version",
                    },
                    {
                        "type": "status",
                        "value": status,
                        "label": "Status",
                    },
                    {
                        "type": "text",
                        "value": last_deploy.isoformat() if last_deploy else "-",
                        "label": "Last Deploy",
                    },
                ]
            )

        return jsonify({"widgets": widgets})


# --- Helpers internes -----------------------------------------------------


def _status_class(value: str) -> str:
    mapping = {
        "success": "status-success",
        "running": "status-running",
        "pending": "status-running",
        "failed": "status-failed",
        "error": "status-failed",
    }
    return mapping.get(value, "status-unknown")


# Module-level client with lazy initialization
_docker_client = None


def _get_docker_client():
    global _docker_client
    if _docker_client is None:
        try:
            _docker_client = docker.from_env()
        except docker.errors.DockerException:
            return None
    return _docker_client


def _get_repo_containers(repo_id: int) -> list[object]:
    """Retourne la liste des containers Docker associés à un repo.

    On utilise COMPOSE_PROJECT_NAME=shiparr_repo_<repo_id> défini dans le Deployer,
    ce qui se retrouve dans le label `com.docker.compose.project`.
    """

    client = _get_docker_client()
    if client is None:
        return []

    label = f"com.docker.compose.project=shiparr_repo_{repo_id}"
    try:
        return list(client.containers.list(all=True, filters={"label": label}))
    except docker.errors.APIError:
        return []


def _container_ok(container: object) -> bool:
    """Détermine si un container est considéré "OK" (running/healthy)."""

    try:
        # type: ignore[union-attr] - docker-py Container a .attrs
        attrs = getattr(container, "attrs", {}) or {}
        state = attrs.get("State", {}) or {}
        health = (state.get("Health") or {}).get("Status")
        status = state.get("Status") or getattr(container, "status", None)
        if health:
            return health == "healthy"
        return status == "running"
    except Exception:
        return False


def _base_css() -> str:
    """CSS commun pour l'UI widget sombre."""

    return """
      body {
        margin: 0;
        padding: 8px;
        font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
        background: #111827;
        color: #e5e7eb;
      }
      h1 {
        margin: 0 0 8px 0;
        font-size: 16px;
      }
      .subtitle {
        font-size: 12px;
        color: #9ca3af;
        margin-bottom: 8px;
      }
      .metrics {
        display: flex;
        gap: 12px;
        font-size: 12px;
        margin-bottom: 8px;
      }
      .metric-label {
        color: #9ca3af;
        text-transform: uppercase;
        letter-spacing: .08em;
        font-size: 11px;
      }
      .metric-value {
        font-weight: 600;
      }
      a {
        color: #60a5fa;
        text-decoration: none;
        font-size: 12px;
      }
      a:hover {
        text-decoration: underline;
      }
      .nav {
        display: flex;
        gap: 8px;
        margin-bottom: 8px;
        font-size: 12px;
      }
      table {
        width: 100%;
        border-collapse: collapse;
        font-size: 13px;
      }
      th, td {
        padding: 4px 6px;
        text-align: left;
        border-bottom: 1px solid #1f2937;
      }
      th {
        background: #0f172a;
        font-weight: 600;
        font-size: 12px;
        text-transform: uppercase;
        letter-spacing: .04em;
      }
      tr:nth-child(even) td {
        background: #020617;
      }
      .repo {
        font-weight: 500;
      }
      .hash code {
        font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace;
        font-size: 11px;
      }
      .status {
        font-size: 11px;
        padding: 2px 6px;
        border-radius: 9999px;
        display: inline-block;
        text-transform: uppercase;
        letter-spacing: .06em;
      }
      .status-success {
        background: rgba(22, 163, 74, 0.15);
        color: #4ade80;
      }
      .status-running {
        background: rgba(59, 130, 246, 0.15);
        color: #60a5fa;
      }
      .status-failed {
        background: rgba(239, 68, 68, 0.15);
        color: #fca5a5;
      }
      .status-unknown {
        background: rgba(148, 163, 184, 0.15);
        color: #e5e7eb;
      }
      .date {
        font-size: 11px;
        white-space: nowrap;
      }
      .header-container {
        display: flex;
        align-items: center;
        gap: 12px;
        margin-bottom: 16px;
        padding-bottom: 16px;
        border-bottom: 1px solid #1f2937;
      }
      .app-logo {
        width: 48px;
        height: 48px;
        object-fit: contain;
      }
      .header-content h1 {
        margin: 0;
        font-size: 18px;
        font-weight: 600;
      }
      .header-content .subtitle {
        margin: 4px 0 0 0;
      }
    """


@require_basic_auth
async def dashy_widget_html() -> Any:
    """Alias legacy pour `/widget/projects/<name>` avec `?project=`.

    Permet de garder la compatibilité avec l'URL documentée dans le guide,
    tout en réutilisant la nouvelle vue projet HTML.
    """

    project_name = request.args.get("project")
    if not project_name:
        return Response("Missing 'project' query parameter", status=400, content_type="text/html")

    return await project_overview_html(project_name)


# --- Nouvelles vues HTML --------------------------------------------------


@require_basic_auth
async def projects_overview_html() -> Any:
    """Vue globale de tous les projets : X/Y repos OK et containers OK."""

    async for session in get_session():
        stmt = select(Project)
        result = await session.execute(stmt)
        projects = result.scalars().all()

        rows_html_parts: list[str] = []

        for project in projects:
            # Repos du projet
            stmt = select(Repository).where(Repository.project_id == project.id)
            repos_result = await session.execute(stmt)
            repos = repos_result.scalars().all()

            repos_total = len(repos)
            repos_ok = 0
            containers_total = 0
            containers_ok = 0

            for repo in repos:
                # Dernier déploiement
                d_stmt = (
                    select(Deployment)
                    .where(Deployment.repository_id == repo.id)
                    .order_by(Deployment.id.desc())
                    .limit(1)
                )
                d_result = await session.execute(d_stmt)
                last_deployment = d_result.scalar_one_or_none()
                if last_deployment and last_deployment.status == "success":
                    repos_ok += 1

                # Containers associés
                containers = _get_repo_containers(repo.id)
                containers_total += len(containers)
                containers_ok += sum(1 for c in containers if _container_ok(c))

            repo_metric = f"{repos_ok}/{repos_total}" if repos_total else "0/0"
            cont_metric = f"{containers_ok}/{containers_total}" if containers_total else "0/0"

            rows_html_parts.append(
                "<tr>"
                f"<td class='repo'>{project.name}</td>"
                f"<td>{repo_metric}</td>"
                f"<td>{cont_metric}</td>"
                f"<td><a href='/widget/projects/{project.name}'>Détails</a></td>"
                "</tr>"
            )

        rows_html = "".join(rows_html_parts) or "<tr><td colspan='4'>Aucun projet</td></tr>"

        html = f"""<!doctype html>
<html>
  <head>
    <meta charset='utf-8' />
    <style>
{_base_css()}
    </style>
  </head>
  <body>
    <div class='header-container'>
      <img src='/static/logo.png' class='app-logo' alt='Shiparr'>
      <div class='header-content'>
        <h1>Shiparr - Projets</h1>
        <div class='subtitle'>Vue d'ensemble des projets, repositories et containers.</div>
      </div>
    </div>
    <table>
      <thead>
        <tr>
          <th>Projet</th>
          <th>Repos OK</th>
          <th>Containers OK</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {rows_html}
      </tbody>
    </table>
  </body>
</html>
"""

        return Response(html, content_type="text/html")


@require_basic_auth
async def project_overview_html(project_name: str) -> Any:
    """Vue détaillée pour un projet : liste des repos + métriques X/X."""

    async for session in get_session():
        stmt = select(Project).where(Project.name == project_name)
        result = await session.execute(stmt)
        project = result.scalar_one_or_none()
        if project is None:
            return Response("Project not found", status=404, content_type="text/html")

        stmt = select(Repository).where(Repository.project_id == project.id)
        result = await session.execute(stmt)
        repos = result.scalars().all()

        rows_html_parts: list[str] = []
        repos_total = len(repos)
        repos_ok = 0
        containers_total = 0
        containers_ok = 0

        for repo in repos:
            d_stmt = (
                select(Deployment)
                .where(Deployment.repository_id == repo.id)
                .order_by(Deployment.id.desc())
                .limit(1)
            )
            d_result = await session.execute(d_stmt)
            last_deployment = d_result.scalar_one_or_none()

            status = "unknown"
            last_hash = "-"
            last_deploy = "-"
            if last_deployment:
                status = last_deployment.status
                last_hash = last_deployment.commit_hash or "-"
                last_deploy = (
                    last_deployment.finished_at or last_deployment.started_at
                )
                if last_deploy:
                    last_deploy = last_deploy.isoformat()
                else:
                    last_deploy = "-"

            if status == "success":
                repos_ok += 1

            containers = _get_repo_containers(repo.id)
            containers_total += len(containers)
            containers_ok += sum(1 for c in containers if _container_ok(c))

            rows_html_parts.append(
                "<tr>"
                f"<td class='repo'>{repo.name}</td>"
                f"<td class='hash'><code>{last_hash}</code></td>"
                f"<td class='status {_status_class(status)}'>{status}</td>"
                f"<td class='date'>{last_deploy}</td>"
                f"<td><a href='/widget/projects/{repo.id}/containers'>Containers</a></td>"
                "</tr>"
            )

        rows_html = "".join(rows_html_parts) or "<tr><td colspan='5'>Aucun repository</td></tr>"

        repo_metric = f"{repos_ok}/{repos_total}" if repos_total else "0/0"
        cont_metric = f"{containers_ok}/{containers_total}" if containers_total else "0/0"

        html = f"""<!doctype html>
<html>
  <head>
    <meta charset='utf-8' />
    <style>
{_base_css()}
    </style>
  </head>
  <body>
    <div class='nav'>
      <a href='/widget/projects'>&larr; Tous les projets</a>
    </div>
    <div class='header-container'>
      <img src='/static/logo.png' class='app-logo' alt='Shiparr'>
      <div class='header-content'>
        <h1>Projet: {project.name}</h1>
      </div>
    </div>
    <div class='metrics'>
      <div>
        <div class='metric-label'>Repos OK</div>
        <div class='metric-value'>{repo_metric}</div>
      </div>
      <div>
        <div class='metric-label'>Containers OK</div>
        <div class='metric-value'>{cont_metric}</div>
      </div>
    </div>
    <table>
      <thead>
        <tr>
          <th>Repository</th>
          <th>Version</th>
          <th>Status</th>
          <th>Last deploy</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {rows_html}
      </tbody>
    </table>
  </body>
</html>
"""

        return Response(html, content_type="text/html")


@require_basic_auth
async def repo_containers_html(repo_id: int) -> Any:
    """Liste des containers pour un repository, avec statut et lien vers logs."""

    async for session in get_session():
        stmt = select(Repository).where(Repository.id == repo_id)
        result = await session.execute(stmt)
        repo = result.scalar_one_or_none()
        if repo is None:
            return Response("Repository not found", status=404, content_type="text/html")

        proj_stmt = select(Project).where(Project.id == repo.project_id)
        proj_result = await session.execute(proj_stmt)
        project = proj_result.scalar_one_or_none()

        containers = _get_repo_containers(repo.id)

        rows_html_parts: list[str] = []
        for c in containers:
            # type: ignore[union-attr]
            raw_name = getattr(c, "name", "<unknown>")
            image = getattr(c, "image", None)

            # Fix IndexError on empty tags
            tags = getattr(image, "tags", []) if image else []
            raw_image_name = tags[0] if tags else "<unknown>"

            status_ok = _container_ok(c)
            status_class = _status_class("success" if status_ok else "failed")
            raw_state = getattr(c, "status", "unknown")
            raw_id = getattr(c, "id", "")

            # HTML escape user controlled values
            name = html_lib.escape(str(raw_name))
            image_name = html_lib.escape(str(raw_image_name))
            state = html_lib.escape(str(raw_state))
            c_id = html_lib.escape(str(raw_id))

            rows_html_parts.append(
                "<tr>"
                f"<td class='repo'>{name}</td>"
                f"<td>{image_name}</td>"
                f"<td class='status {status_class}'>{state}</td>"
                f"<td><a href='/widget/projects/{repo.id}/containers/logs?container={c_id}&tail=200' target='_blank' rel='noreferrer noopener'>logs -f</a></td>"
                "</tr>"
            )

        rows_html = "".join(rows_html_parts) or "<tr><td colspan='4'>Aucun container pour ce repository</td></tr>"

        project_name = project.name if project is not None else "?"

        html = f"""<!doctype html>
<html>
  <head>
    <meta charset='utf-8' />
    <style>
{_base_css()}
    </style>
  </head>
  <body>
    <div class='nav'>
      <a href='/widget/projects'>&larr; Tous les projets</a>
      <a href='/widget/projects/{project_name}'>Projet: {project_name}</a>
    </div>
    <div class='header-container'>
      <img src='/static/logo.png' class='app-logo' alt='Shiparr'>
      <div class='header-content'>
        <h1>Containers - {project_name} / {repo.name}</h1>
      </div>
    </div>
    <table>
      <thead>
        <tr>
          <th>Container</th>
          <th>Image</th>
          <th>Status</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {rows_html}
      </tbody>
    </table>
  </body>
</html>
"""

        return Response(html, content_type="text/html")


@require_basic_auth
async def repo_container_logs_html(repo_id: int) -> Any:
    """Affiche les logs d'un container pour un repository donné."""

    container_id = request.args.get("container")
    if not container_id:
        return Response("Missing 'container' query parameter", status=400, content_type="text/html")

    tail = request.args.get("tail", type=int) or 200

    try:
        client = _get_docker_client()
        container = client.containers.get(container_id)
        raw_logs = container.logs(tail=tail).decode("utf-8", errors="ignore")
        safe_logs = html_lib.escape(raw_logs)
    except Exception as exc:  # pragma: no cover - best effort UI
        return Response(f"Error fetching logs: {exc}", status=500, content_type="text/html")

    # On ne touche pas au repo/projet, ce n'est que pour l'affichage
    html = f"""<!doctype html>
<html>
  <head>
    <meta charset='utf-8' />
    <style>
{_base_css()}
  html, body {{
    height: 95%;
  }}
      body {{
        display: flex;
        flex-direction: column;
      }}
      .logs-wrapper {{
        flex: 1;
        display: flex;
        flex-direction: column;
        min-height: 0;
      }}
      pre {{
        background: #020617;
        border-radius: 4px;
        padding: 8px;
        font-size: 11px;
        overflow: auto;
        flex: 1;
        line-height: 1.4;
        margin-top: 8px;
      }}
    </style>
  </head>
  <body>
    <div class='logs-wrapper'>
      <div class='nav'>
        <a href='/widget/projects'>&larr; Tous les projets</a>
        <a href='/widget/projects/{repo_id}/containers'>&larr; Containers</a>
      </div>
      <div class='header-container'>
        <img src='/static/logo.png' class='app-logo' alt='Shiparr'>
        <div class='header-content'>
          <h1>Logs -f container</h1>
          <div class='subtitle'>Dernières {tail} lignes du container {html_lib.escape(container_id)}</div>
        </div>
      </div>
      <pre>{safe_logs}</pre>
    </div>
  </body>
</html>
"""

    return Response(html, content_type="text/html")
