"""Notification system for Shiparr using Shoutrrr CLI.

Responsabilités:
- Envoyer des notifications via Shoutrrr
- Formater les messages selon le contexte (success/failure)
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Iterable, List

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .config import LoadedConfig
from .logging_utils import get_logger
from .models import Deployment, Repository, Project


logger = get_logger(__name__)


class NotificationError(RuntimeError):
    """Erreur lors de l'envoi de notification."""


class NotificationManager:
    """Envoie des notifications via la CLI `shoutrrr`.
    
    Cette classe sait également récupérer les URLs de notification depuis la
    configuration YAML (LoadedConfig) et la base de données.
    """

    def __init__(
        self,
        config: LoadedConfig,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self.config = config
        self.session_factory = session_factory

    async def notify(self, urls: list[str], event: str, deployment: Deployment) -> None:
        """Envoie une notification vers toutes les URLs données.

        Les erreurs sont loggées mais ne lèvent pas d'exception (ne doivent pas bloquer le déploiement).
        """

        message = self.format_message(event, deployment)
        logger.info(
            "Sending notifications",
            extra={"event": event, "deployment_id": deployment.id, "url_count": len(urls)},
        )

        async def _send(url: str) -> None:
            try:
                proc = await asyncio.create_subprocess_exec(
                    "shoutrrr",
                    "send",
                    "-u",
                    url,
                    "-m",
                    message,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await proc.communicate()

                if proc.returncode != 0:
                    error_msg = stderr.decode().strip()
                    logger.error(
                        "Shoutrrr failed",
                        extra={
                            "url": url,
                            "returncode": proc.returncode,
                            "stderr": error_msg,
                        },
                    )
                else:
                    logger.info("Notification sent", extra={"url": url})

            except FileNotFoundError:
                logger.warning("Shoutrrr executable not found. Notifications disabled.")
            except Exception as e:
                logger.exception("Failed to send notification", extra={"url": url, "error": str(e)})

        await asyncio.gather(*[_send(url) for url in urls])

    def format_message(self, event: str, deployment: Deployment) -> str:
        """Formate un message texte simple pour Shoutrrr."""

        status = deployment.status
        repo_id = deployment.repository_id
        started = deployment.started_at or datetime.utcnow()
        finished = deployment.finished_at or datetime.utcnow()
        duration = (finished - started).total_seconds()

        return (
            f"Shiparr {event.upper()} - repo={repo_id} "
            f"status={status} duration={duration:.1f}s deployment_id={deployment.id}"
        )

    async def notify_for_deployment(self, event: str, deployment: Deployment) -> None:
        """Récupère les URLs de notification pour un déploiement donné.

        La configuration est lue depuis LoadedConfig:
        - `project.global_notifications[event]`
        - `repository.notifications[event]`
        """

        async with self.session_factory() as session:
            repo = await session.get(Repository, deployment.repository_id)
            if repo is None:
                logger.warning(
                    "Repository not found when sending notifications",
                    extra={"deployment_id": deployment.id},
                )
                return

            project = await session.get(Project, repo.project_id)
            if project is None:
                logger.warning(
                    "Project not found when sending notifications",
                    extra={"deployment_id": deployment.id, "repository_id": repo.id},
                )
                return

        project_cfg = self.config.projects.get(project.name)
        if project_cfg is None:
            logger.warning(
                "No project config found when sending notifications",
                extra={"project_name": project.name},
            )
            return

        repo_cfg = project_cfg.repositories.get(repo.name)  # type: ignore[arg-type]
        if repo_cfg is None:
            logger.warning(
                "No repo config found when sending notifications",
                extra={"project_name": project.name, "repository_name": repo.name},
            )
            return

        urls: List[str] = []
        if repo_cfg.notifications and event in repo_cfg.notifications:
            urls.extend(repo_cfg.notifications[event])

        if project_cfg.global_notifications and event in project_cfg.global_notifications:
            urls.extend(project_cfg.global_notifications[event])

        if not urls:
            logger.info(
                "No notification URLs configured for event",
                extra={"event": event, "project": project.name, "repository": repo.name},
            )
            return

        await self.notify(urls, event, deployment)
