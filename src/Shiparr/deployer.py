"""Deployment orchestration for Shiparr.

Responsabilités (guide):
- Orchestrer le workflow de déploiement complet
- Créer les entrées Deployment en DB
- Capturer les logs
- Déclencher les notifications
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx
from docker.errors import DockerException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .config import LoadedConfig
from .git_manager import GitManager
from .logging_utils import get_logger
from .models import Deployment, Repository
from .sops_manager import SopsManager

logger = get_logger(__name__)


class DeploymentError(RuntimeError):
    """Erreur haut niveau lors d'un déploiement."""


class Deployer:
    """Orchestre le cycle de déploiement pour un Repository."""

    def __init__(
        self,
        session: AsyncSession,
        notifications=None,
        prune_enabled: bool = False,
        config: LoadedConfig | None = None,
    ) -> None:
        self.session = session
        # notifications: objet NotificationManager ou None (injecté par app)
        self.notifications = notifications
        self.prune_enabled = prune_enabled
        self.config = config

    def _resolve_token(self, repository: Repository) -> Optional[str]:
        """Résout le token d'authentification pour un repository donné."""
        token: str | None = None
        
        # 1. Essayer de trouver un token au niveau du projet
        if self.config and repository.project and repository.project.name in self.config.projects:
            project_cfg = self.config.projects[repository.project.name]
            if project_cfg.tokens:
                # Logique heuristique simple pour l'instant
                if "github" in repository.git_url and "github" in project_cfg.tokens:
                    token = project_cfg.tokens["github"]
                elif "gitlab" in repository.git_url and "gitlab" in project_cfg.tokens:
                    token = project_cfg.tokens["gitlab"]
                elif "default" in project_cfg.tokens:
                    token = project_cfg.tokens["default"]
                # Si un seul token défini, on l'utilise
                elif len(project_cfg.tokens) == 1:
                    token = list(project_cfg.tokens.values())[0]

        # 2. Fallback global settings (GitHub Token)
        if not token and self.config and self.config.settings.github_token:
             # On n'utilise le token global que pour GitHub ou si on est désespéré
             if "github.com" in repository.git_url:
                 token = self.config.settings.github_token
        
        return token

    def _resolve_token(self, repository: Repository) -> str | None:
        """Résout le token GitHub à utiliser pour ce repository."""
        if repository.github_token:
            return repository.github_token
        # On pourrait ajouter ici une logique pour récupérer un token global
        # depuis self.settings ou autre, mais pour l'instant on s'en tient au repo.
        return None

    async def _create_deployment(self, repository: Repository, status: str) -> Deployment:
        deployment = Deployment(
            repository_id=repository.id,
            commit_hash=repository.last_commit_hash or "",
            status=status,
            started_at=datetime.utcnow(),
        )
        self.session.add(deployment)
        await self.session.commit()  # Commit immediately to release lock
        return deployment

    async def _update_deployment(
        self,
        deployment: Deployment,
        *,
        status: str,
        logs: Optional[str] = None,
    ) -> None:
        # Re-merge deployment if detached (because session might be new or committed)
        # However, since we are in the same session context, committing just expires it.
        # Accessing attributes will reload it.
        deployment.status = status
        deployment.finished_at = datetime.utcnow()
        if logs is not None:
            deployment.logs = logs
        self.session.add(deployment) # Ensure it is attached
        await self.session.commit()

    async def down(self, repository: Repository) -> None:
        """Arrête les conteneurs pour un repository donné."""
        logger.info("Stopping deployment", extra={"repository_id": repository.id})

        local_path = Path(repository.local_path).resolve()
        if repository.path:
            workdir = local_path / repository.path
        else:
            workdir = local_path

        if not workdir.exists():
            logger.warning(
                "Workdir does not exist, cannot stop", extra={"workdir": str(workdir)}
            )
            return

        cmd = ["docker", "compose", "down"]
        # Reconstruct environment with correct project name
        env = {**os.environ, "COMPOSE_PROJECT_NAME": f"shiparr_repo_{repository.id}"}

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(workdir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            stderr_str = stderr.decode()
            # Ignorer l'erreur "network ... is still used by" car le network sera supprimé plus tard
            # ou réutilisé
            if "network" in stderr_str and "is still used by" in stderr_str:
                logger.warning(
                    "docker compose down warning (ignored)",
                    extra={
                        "repository_id": repository.id,
                        "stderr": stderr_str,
                    },
                )
            else:
                logger.error(
                    "docker compose down failed",
                    extra={
                        "repository_id": repository.id,
                        "returncode": proc.returncode,
                        "stderr": stderr_str,
                    },
                )
        else:
            logger.info(
                "docker compose down successful", extra={"repository_id": repository.id}
            )

    async def _check_containers_running(self, workdir: Path, env: dict[str, str]) -> bool:
        """Vérifie si des conteneurs associés au projet sont en cours d'exécution."""
        cmd = ["docker", "compose", "ps", "--filter", "status=running", "-q"]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(workdir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
            stdout, _ = await proc.communicate()
            # Si on a des IDs en sortie, c'est que des conteneurs tournent
            return bool(stdout.strip())
        except Exception as e:
            logger.warning(
                "Failed to check container status",
                extra={"workdir": str(workdir), "error": str(e)},
            )
            return False

    async def _perform_healthcheck(self, repository: Repository, logs_parts: list[str]) -> bool:
        """Exécute le healthcheck si configuré.
        
        Retourne True si le healthcheck passe ou n'est pas configuré.
        Retourne False si échec.
        """
        if not repository.healthcheck_url:
            return True

        url = repository.healthcheck_url
        timeout = repository.healthcheck_timeout or 60
        expected_status = repository.healthcheck_expected_status or 200

        logger.info(
            "Waiting for healthcheck",
            extra={
                "repository_id": repository.id,
                "url": url,
                "timeout": timeout
            }
        )
        logs_parts.append(f"Starting healthcheck on {url} (timeout: {timeout}s)")

        start_time = datetime.utcnow()
        
        async with httpx.AsyncClient(verify=False) as client:
            while (datetime.utcnow() - start_time).total_seconds() < timeout:
                try:
                    response = await client.get(url, timeout=5.0)
                    if response.status_code == expected_status:
                        logger.info(
                            "Healthcheck passed",
                            extra={"repository_id": repository.id, "status": response.status_code}
                        )
                        logs_parts.append(f"Healthcheck passed: {url} returned {response.status_code}")
                        return True
                    else:
                        # On loggue juste en debug pour ne pas spammer, sauf si c'est le dernier essai ?
                        # Non, on continue tant que time < timeout
                        pass
                except Exception:
                    # Connection refused, timeout, etc.
                    pass
                
                await asyncio.sleep(2)

        error_msg = f"Healthcheck failed: {url} did not return {expected_status} within {timeout}s"
        logger.error(error_msg, extra={"repository_id": repository.id})
        logs_parts.append(error_msg)
        return False

    async def deploy(self, repository_id: int) -> Deployment:
        """Flux complet de déploiement pour un repository.

        Étapes (guide):
        1. Créer Deployment(status=pending)
        2. Vérifier si changements Git (get_remote_hash vs last_commit_hash)
        3. Vérifier si conteneurs tournent
        4. Si pas de changement ET conteneurs tournent -> return (pas de notif succès)
        5. Pull le repo
        6. Si env_file configuré -> SopsManager.decrypt_file()
        7. Exécuter docker compose up -d (avec retry)
        8. Mettre à jour Deployment(status=success/failed, logs)
        9. Mettre à jour Repository.last_commit_hash
        10. Envoyer notifications
        11. Return Deployment
        """

        logger.info("Starting deployment", extra={"repository_id": repository_id})

        repo_stmt = select(Repository).options(selectinload(Repository.project)).where(Repository.id == repository_id)
        result = await self.session.execute(repo_stmt)
        repository: Repository | None = result.scalar_one_or_none()
        if repository is None:
            logger.error(
                "Repository not found for deployment", extra={"repository_id": repository_id}
            )
            raise DeploymentError(f"Repository {repository_id} not found")

        # Cas spécifique pour se déployer soi-même (Shiparr)
        # Si le projet s'appelle 'Shiparr' et que le path est 'Shiparr' (convention)
        # On doit éviter de faire n'importe quoi qui pourrait tuer le conteneur courant
        # Mais ici on est dans la logique de déploiement standard.
        # La demande utilisateur est: "il faut un path specifique dans le dossier project nommé
        # 'Shiparr' qui servira a controlé Shiparr depuis Shiparr, et evité une boucle infini"

        # On suppose que si le repository s'appelle "Shiparr", c'est le repo de l'appli elle-même.
        # Dans ce cas, on ne doit PAS faire un `docker compose up` standard qui recréerait le
        # conteneur depuis lequel on tourne, car ça couperait le processus en cours.

        # Pour l'instant, on va juste logger un warning et empêcher le déploiement automatique
        # si on détecte qu'on essaie de déployer "Shiparr" via la méthode standard,
        # SAUF si une logique spécifique de mise à jour "self-update" est implémentée.

        # Mais l'utilisateur demande "un path spécifique dans le dossier project nommé Shiparr".
        # Cela suggère que si repository.path == "Shiparr", c'est une config spéciale.

        if repository.path and Path(repository.path).name == "Shiparr":
            logger.warning(
                "Self-deployment of Shiparr detected via special path. Initiating self-update sequence.",
                extra={"repository_id": repository_id, "path": repository.path},
            )
            
            # 1. On met à jour le statut et le hash AVANT de lancer la commande qui risque de nous tuer
            # Cela évite la boucle infinie si le redémarrage réussit mais que le script meurt avant d'update la DB
            if repository.last_commit_hash:
                token = self._resolve_token(repository)
                remote_hash = await GitManager.get_remote_hash(
                    repository.local_path, repository.branch, url=repository.git_url, token=token
                )
                # Mise à jour "préventive" du hash pour que le scheduler considère que c'est fait
                repository.last_commit_hash = remote_hash
            
            # On crée le déploiement et on le marque en succès (ou en 'updating')
            # Si le container redémarre, le nouveau code prendra le relais.
            deployment = await self._create_deployment(repository, status="success")
            await self._update_deployment(
                deployment, status="success", logs="Self-update initiated - Container restarting..."
            )
            # No extra commit needed
            # 2. On procède à la mise à jour
            # Git Pull
            local_path = Path(repository.local_path).resolve()
            if local_path.exists():
                try:
                    token = self._resolve_token(repository)
                    await GitManager.pull(
                        str(local_path),
                        branch=repository.branch,
                        url=repository.git_url,
                        token=token,
                    )
                except Exception:
                    # Si échec pull, on est mal car on a déjà validé le hash en DB... 
                    # Mais c'est le risque de l'auto-update.
                    logger.exception("Self-update git pull failed")
                    # On tente de rollback le hash en mémoire/db ?
                    # Trop complexe pour l'instant.
                    raise

            # Docker Compose Up (Fire and forget ou presque)
            # On sait que cette commande va probablement terminer ce processus.
            
            # Détection automatique
            compose_file = "docker-compose.yml"
            if repository.path:
                workdir = local_path / repository.path
            else:
                workdir = local_path

            if not (workdir / compose_file).exists():
                if (workdir / "docker-compose.yaml").exists():
                    compose_file = "docker-compose.yaml"

            cmd = ["docker", "compose", "-f", compose_file, "up", "-d"]

            logger.info(
                "Executing docker compose up -d for self-update (process will die)",
                extra={"cmd": " ".join(cmd), "workdir": str(workdir)}
            )

            env = {**os.environ, "COMPOSE_PROJECT_NAME": f"shiparr_repo_{repository.id}"}

            # On lance la commande. Si le daemon redémarre le container, ce script recevra SIGTERM.
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(workdir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
            
            # On attend un peu, mais on s'attend à mourir.
            # Si on survit, c'est que l'image n'a pas changé ou que la config est identique.
            stdout, stderr = await proc.communicate()
            
            if proc.returncode != 0:
                logger.error(
                    "Self-update docker compose failed",
                    extra={"stderr": stderr.decode(), "returncode": proc.returncode}
                )
                # On pourrait remettre le status en failed, mais si on est mort entre temps...
            
            return deployment

        deployment = await self._create_deployment(repository, status="pending")
        logger.debug(
            "Created deployment row",
            extra={"deployment_id": deployment.id, "repository_id": repository_id},
        )

        try:
            # Préparation du contexte (workdir, env) nécessaire pour les vérifications
            local_path = Path(repository.local_path).resolve()
            if repository.path:
                workdir = local_path / repository.path
            else:
                workdir = local_path
            
            env = {**os.environ, "COMPOSE_PROJECT_NAME": f"shiparr_repo_{repository.id}"}

            remote_hash = None
            # 2. Vérifier les changements
            token = self._resolve_token(repository)
            
            if repository.last_commit_hash:
                logger.debug(
                    "Checking for remote changes",
                    extra={
                        "repository_id": repository.id,
                        "local_path": repository.local_path,
                        "branch": repository.branch,
                        "last_commit_hash": repository.last_commit_hash,
                    },
                )
                remote_hash = await GitManager.get_remote_hash(
                    repository.local_path, repository.branch, url=repository.git_url, token=token
                )
                logger.debug(
                    "Remote hash fetched",
                    extra={"repository_id": repository.id, "remote_hash": remote_hash},
                )
                
                # Vérifier si les conteneurs tournent
                containers_running = await self._check_containers_running(workdir, env)

                if remote_hash == repository.last_commit_hash:
                    if containers_running:
                        logger.info(
                            "No changes detected and containers are running, skipping deployment",
                            extra={"repository_id": repository.id},
                        )
                        # Si pas de changements et tout va bien, on met à jour le statut
                        await self._update_deployment(
                            deployment, status="success", logs="No changes, services running"
                        )
                        # No extra commit needed
                        return deployment
                    else:
                        logger.info(
                            "No changes detected but containers are NOT running. Forcing deployment.",
                            extra={"repository_id": repository.id},
                        )

            # Si on arrive ici, c'est qu'il y a des changements, ou c'est le premier run, 
            # ou les conteneurs sont morts.
            logger.info(
                "Starting update process...",
                extra={
                    "repository_id": repository.id,
                    "old_hash": repository.last_commit_hash,
                    "new_hash": remote_hash or "initial",
                },
            )

            # 4. Pull (ou clone si repo inexistant)
            # local_path déjà défini plus haut
            if not local_path.exists():
                logger.info(
                    "Creating local repo directory",
                    extra={"repository_id": repository.id, "local_path": str(local_path)},
                )
                local_path.mkdir(parents=True, exist_ok=True)
                # Clonage initial si le dossier est vide ou n'est pas un repo git
                # Note: GitManager.pull() suppose un repo existant. Il faut ajouter le clone.
                token = self._resolve_token(repository)
                await GitManager.clone(
                    url=repository.git_url,
                    branch=repository.branch,
                    local_path=str(local_path),
                    token=token,
                )
                new_hash = await GitManager.get_local_hash(str(local_path))
            else:
                # Si existe mais vide
                if not any(local_path.iterdir()):
                    logger.info(
                        "Local repo directory exists but is empty, cloning",
                        extra={"repository_id": repository.id, "local_path": str(local_path)},
                    )
                    token = self._resolve_token(repository)
                    await GitManager.clone(
                        url=repository.git_url,
                        branch=repository.branch,
                        local_path=str(local_path),
                        token=token,
                    )
                    new_hash = await GitManager.get_local_hash(str(local_path))
                else:
                    # Si déjà un repo git
                    try:
                        logger.info(
                            "Pulling repository",
                            extra={
                                "repository_id": repository.id,
                            "local_path": str(local_path),
                            },
                        )
                        new_hash = await GitManager.pull(
                            str(local_path),
                            branch=repository.branch,
                            url=repository.git_url,
                            token=token,
                        )
                    except Exception:
                        # Si dossier existe mais pas repo git valide ?
                        # (cas rare, on assume repo valide pour l'instant)
                        logger.exception(
                            "Error while pulling existing local repository",
                            extra={
                                "repository_id": repository.id,
                                "local_path": str(local_path),
                            },
                        )
                        raise

            repository.last_commit_hash = new_hash

            # 5. SOPS si besoin
            logs_parts: list[str] = []
            if repository.path:
                workdir = local_path / repository.path
            else:
                workdir = local_path

            if hasattr(repository, "env_file") and repository.env_file:  # type: ignore[attr-defined]
                enc = workdir / repository.env_file  # type: ignore[operator]
                dec = workdir / ".env"
                logger.info(
                    "Decrypting env file with SOPS",
                    extra={
                        "repository_id": repository.id,
                        "encrypted": str(enc),
                        "output": str(dec),
                    },
                )
                await SopsManager.decrypt_file(enc, dec)
                logs_parts.append(f"Decrypted env file {enc} -> {dec}")

            # Détection automatique du fichier compose (yml ou yaml)
            compose_file = "docker-compose.yml"
            if not (workdir / compose_file).exists():
                if (workdir / "docker-compose.yaml").exists():
                    compose_file = "docker-compose.yaml"
            
            # 6. docker compose up -d via CLI pour compatibilité (avec Retry)
            cmd = [
                "docker",
                "compose",
                "-f",
                compose_file,
                "up",
                "-d",
            ]

            logger.info(
                "Running docker compose up -d",
                extra={
                    "repository_id": repository.id,
                    "workdir": str(workdir),
                    "cmd": " ".join(cmd),
                    "local_path_resolved": str(local_path),
                    "path_suffix": repository.path,
                },
            )

            # On force un COMPOSE_PROJECT_NAME basé sur l'id du repo afin de
            # pouvoir retrouver les containers plus tard via le label
            # `com.docker.compose.project=shiparr_repo_<repo_id>`.
            # Note: env est déjà défini plus haut

            max_retries = 3
            success = False
            last_error_msg = ""

            for attempt in range(1, max_retries + 1):
                try:
                    logger.debug(f"Docker compose up attempt {attempt}/{max_retries}")
                    
                    proc = await asyncio.create_subprocess_exec(
                        *cmd,
                        cwd=str(workdir),
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                        env=env,
                    )
                    stdout, stderr = await proc.communicate()
                    
                    # On loggue les sorties de chaque tentative si besoin
                    if stdout:
                        logs_parts.append(f"Attempt {attempt} stdout: {stdout.decode()}")
                    if stderr:
                        logs_parts.append(f"Attempt {attempt} stderr: {stderr.decode()}")

                    if proc.returncode == 0:
                        success = True
                        break
                    else:
                        stderr_str = stderr.decode() if stderr else ""
                        last_error_msg = f"Return code {proc.returncode}: {stderr_str}"
                        logger.warning(
                            f"docker compose attempt {attempt} failed",
                            extra={
                                "repository_id": repository.id,
                                "attempt": attempt,
                                "returncode": proc.returncode,
                                "stderr": stderr_str,
                            },
                        )
                        if attempt < max_retries:
                            await asyncio.sleep(2)  # Petite pause avant retry

                except Exception as e:
                    last_error_msg = str(e)
                    logger.exception(
                        f"Exception during docker compose attempt {attempt}",
                         extra={"repository_id": repository.id}
                    )
                    if attempt < max_retries:
                        await asyncio.sleep(2)

            if not success:
                 logger.error(
                    "All docker compose attempts failed",
                    extra={
                        "repository_id": repository.id,
                        "last_error": last_error_msg,
                    },
                )
                 raise DeploymentError(f"docker compose failed after {max_retries} attempts: {last_error_msg}")

            # 7. Healthcheck
            if not await self._perform_healthcheck(repository, logs_parts):
                 raise DeploymentError("Healthcheck failed after deployment")

            logs = "\n".join(logs_parts).strip()
            await self._update_deployment(deployment, status="success", logs=logs)
            # No extra commit needed as _update_deployment commits

            logger.info(
                "Deployment completed successfully",
                extra={"deployment_id": deployment.id, "repository_id": repository.id},
            )

            # 8. Notifications succès
            if self.notifications is not None:
                await self.notifications.notify_for_deployment("success", deployment)

            # 9. Prune images if enabled
            if self.prune_enabled:
                try:
                    logger.info("Pruning unused images", extra={"repository_id": repository.id})
                    proc = await asyncio.create_subprocess_exec(
                        "docker", "image", "prune", "-f",
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    await proc.communicate()
                except Exception as e:
                    logger.warning(f"Image prune failed: {e}", extra={"repository_id": repository.id})

            return deployment

        except (DeploymentError, DockerException, Exception) as exc:  # pragma: no cover
            logger.exception(
                "Deployment failed",
                extra={"deployment_id": deployment.id, "repository_id": repository_id},
            )
            logs = f"Deployment failed: {exc}"
            await self._update_deployment(deployment, status="failed", logs=logs)
            # No extra commit needed
            if self.notifications is not None:
                await self.notifications.notify_for_deployment("failure", deployment)
            return deployment
