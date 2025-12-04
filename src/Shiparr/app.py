"""Quart application entrypoint for Shiparr."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from quart import Quart
from sqlalchemy import select

from .config import ConfigLoader, LoadedConfig, Settings
from .database import dispose_engine, init_db
from . import database
from .logging_utils import configure_logging, get_logger
from .models import Project, Repository
from .routes import create_blueprint

if TYPE_CHECKING:
    from .notifications import NotificationManager


logger = get_logger(__name__)


async def _sync_config_to_db(
    loaded: LoadedConfig, notifications: Optional[NotificationManager] = None
) -> None:
    """Synchronise les Project/Repository en base avec la configuration YAML.

    - Crée les projets/repos manquants
    - Met à jour les repos existants
    - Supprime les repos qui n'existent plus dans la config

    Optimisations / gardes supplémentaires:
    - Si plusieurs projets référencent le *même* dépôt Git (même ``local_path``
      et même branche), on laisse la DB créer un Repository par projet mais on
      peut mutualiser les appels Git via un cache dans :mod:`git_manager`.
    - Si deux repositories partagent exactement le même ``local_path`` mais
      déclarent une ``url`` ou une ``branch`` différente, cela représente une
      configuration invalide (même dossier disque pour deux remotes différents).
      Dans ce cas, on log un warning et on ignore la définition conflictuelle.
    """

    if database.async_session_factory is None:  # type: ignore[truthy-function]
        logger.error("async_session_factory is None in _sync_config_to_db - DB not initialised")
        return

    # Détection préalable des conflits de local_path entre projets/repos.
    # Clé: chemin absolu -> (url, branch, project, repo_name)
    local_path_index: dict[str, tuple[str, str, str, str]] = {}
    repos_to_skip: set[tuple[str, str]] = set()

    for project_cfg in loaded.projects.values():
        for repo_name, repo_cfg in project_cfg.repositories.items():
            local_path_str = str(Path(repo_cfg.local_path).resolve())
            existing = local_path_index.get(local_path_str)
            if existing is None:
                local_path_index[local_path_str] = (
                    repo_cfg.url,
                    repo_cfg.branch,
                    project_cfg.project,
                    repo_name,
                )
                continue

            existing_url, existing_branch, existing_project, existing_repo = existing
            # Même dossier mais URL/branche différentes -> configuration incohérente
            if repo_cfg.url != existing_url or repo_cfg.branch != existing_branch:
                logger.warning(
                    "Conflicting repository configuration detected for shared local_path; "
                    "skipping duplicate entry",
                    extra={
                        "local_path": local_path_str,
                        "first_project": existing_project,
                        "first_repository": existing_repo,
                        "first_url": existing_url,
                        "first_branch": existing_branch,
                        "conflicting_project": project_cfg.project,
                        "conflicting_repository": repo_name,
                        "conflicting_url": repo_cfg.url,
                        "conflicting_branch": repo_cfg.branch,
                    },
                )
                repos_to_skip.add((project_cfg.project, repo_name))
            else:
                # Même dépôt (url/branche) et même dossier local: on log pour debug.
                logger.info(
                    "Multiple repositories share the same Git local_path and branch; "
                    "Git remote checks will be mutualised.",
                    extra={
                        "local_path": local_path_str,
                        "branch": repo_cfg.branch,
                        "project": project_cfg.project,
                        "repository": repo_name,
                    },
                )

    async with database.async_session_factory() as session:  # type: ignore[call-arg]
        # Index existant en mémoire
        logger.debug("Sync DB: loading existing projects from database")
        existing_projects = {
            p.name: p
            for p in (await session.execute(select(Project))).scalars().all()
        }

        created_projects = 0
        created_repos = 0
        updated_repos = 0
        deleted_repos = 0

        for project_cfg in loaded.projects.values():
            project = existing_projects.get(project_cfg.project)
            if project is None:
                logger.info(
                    "Creating project in DB from config",
                    extra={"project": project_cfg.project},
                )
                project = Project(
                    name=project_cfg.project,
                    config_file=f"{project_cfg.project}.yaml",
                )
                session.add(project)
                await session.flush()
                existing_projects[project.name] = project
                created_projects += 1

            # Charger les repos existants pour ce projet
            result = await session.execute(
                select(Repository).where(Repository.project_id == project.id)
            )
            existing_repos = {r.name: r for r in result.scalars().all()}

            # Upsert depuis la config
            for repo_name, repo_cfg in project_cfg.repositories.items():
                # Si ce repo a été marqué comme conflictuel (même local_path mais
                # url/branche différentes qu'un autre repo), on l'ignore.
                if (project_cfg.project, repo_name) in repos_to_skip:
                    logger.debug(
                        "Skipping repository with conflicting local_path configuration",
                        extra={
                            "project": project_cfg.project,
                            "repository": repo_name,
                            "local_path": repo_cfg.local_path,
                        },
                    )
                    continue

                repo = existing_repos.get(repo_name)
                if repo is None:
                    logger.info(
                        "Creating repository in DB from config",
                        extra={
                            "project": project_cfg.project,
                            "repository": repo_name,
                            "git_url": repo_cfg.url,
                        },
                    )
                    repo = Repository(
                        project_id=project.id,
                        name=repo_cfg.name,
                        git_url=repo_cfg.url,
                        branch=repo_cfg.branch,
                        path=repo_cfg.path,
                        local_path=repo_cfg.local_path,
                        check_interval=repo_cfg.check_interval,
                    )
                    session.add(repo)
                    created_repos += 1
                else:
                    # Si l'URL ou la branche a changé, on doit nettoyer l'existant
                    # pour forcer un re-clone propre.
                    if repo.git_url != repo_cfg.url or repo.branch != repo_cfg.branch:
                        logger.info(
                            "Repository config changed (url/branch), resetting...",
                            extra={
                                "project": project_cfg.project,
                                "repository": repo_name,
                                "old_url": repo.git_url,
                                "new_url": repo_cfg.url,
                                "old_branch": repo.branch,
                                "new_branch": repo_cfg.branch,
                            },
                        )

                        # Protection spécifique contre le suicide de Shiparr
                        if repo.path and "Shiparr" in str(repo.path):
                            logger.warning(
                                "Shiparr self-repo config changed. "
                                "Skipping HARD RESET (down/rm) to avoid killing the running process. "
                                "Only updating DB config to trigger future update.",
                                extra={"repository": repo_name},
                            )
                            # On efface le hash pour forcer un git pull au prochain cycle
                            repo.last_commit_hash = None
                        else:
                            # Logique standard: on arrête et on supprime tout
                            
                            # On arrête les conteneurs existants
                            # Import local pour éviter les cycles si Deployer importait app...
                            # (ce n'est pas le cas ici mais c'est plus sûr dans cette fonction
                            # utilitaire)
                            from .deployer import Deployer

                            deployer = Deployer(session=session, notifications=notifications)
                            try:
                                await deployer.down(repo)
                            except Exception as e:
                                logger.error(f"Failed to stop containers during reset: {e}")

                            # On supprime le dossier local
                            if repo.local_path:
                                local_path_obj = Path(repo.local_path)
                                if local_path_obj.exists():
                                    try:
                                        shutil.rmtree(local_path_obj)
                                        logger.info(f"Deleted local path: {repo.local_path}")
                                    except Exception as e:
                                        logger.error(f"Failed to delete {repo.local_path}: {e}")

                            # On force le redéploiement en effaçant le hash
                            repo.last_commit_hash = None

                    logger.debug(
                        "Updating repository from config",
                        extra={
                            "project": project_cfg.project,
                            "repository": repo_name,
                        },
                    )
                    updated_repos += 1
                    repo.git_url = repo_cfg.url
                    repo.branch = repo_cfg.branch
                    repo.path = repo_cfg.path
                    repo.local_path = repo_cfg.local_path
                    repo.check_interval = repo_cfg.check_interval

            # Supprimer les repos qui ne sont plus dans la config
            names_in_config = set(project_cfg.repositories.keys())
            for repo_name, repo in existing_repos.items():
                if repo_name not in names_in_config:
                    logger.info(
                        "Deleting repository no longer present in config",
                        extra={"project": project_cfg.project, "repository": repo_name},
                    )
                    session.delete(repo)
                    deleted_repos += 1

        await session.commit()
        logger.debug(
            "Config sync to DB completed",
            extra={
                "projects_created": created_projects,
                "repos_created": created_repos,
                "repos_updated": updated_repos,
                "repos_deleted": deleted_repos,
            },
        )


def create_app() -> Quart:
    app = Quart(__name__)

    settings = Settings()  # chargé depuis l'environnement
    app.config["Shiparr_SETTINGS"] = settings

    logger.info(
        "Creating Quart app with settings",
        extra={
            "config_path": str(settings.config_path),
            "data_path": str(settings.data_path),
            "port": settings.port,
            "log_level": settings.log_level,
        },
    )

    @app.before_serving
    async def startup() -> None:  # type: ignore[override]
        # 1. Init DB
        db_path = Path(settings.data_path) / "Shiparr.db"
        logger.debug("Initializing database", extra={"db_path": str(db_path)})
        await init_db(db_path)

        # 2. Charger configuration projets
        # Créer le dossier de config s'il n'existe pas encore pour éviter les
        # erreurs lors des premiers démarrages/tests.
        settings.config_path.mkdir(parents=True, exist_ok=True)
        logger.debug(
            "Loading project configuration", extra={"config_path": str(settings.config_path)}
        )
        loader = ConfigLoader(settings=settings)
        loaded = loader.load()
        logger.debug(
            "Project configuration loaded", extra={"projects": list(loaded.projects.keys())}
        )
        app.config["Shiparr_CONFIG"] = loaded

        # 3. Initialiser le gestionnaire de notifications avec la config + DB
        from .notifications import NotificationManager

        if database.async_session_factory is not None:  # type: ignore[truthy-function]
            logger.debug("Initialising NotificationManager")
            app.config["Shiparr_NOTIFICATIONS"] = NotificationManager(
                config=loaded,
                session_factory=database.async_session_factory,  # type: ignore[arg-type]
            )
        else:
            logger.warning("Notifications disabled because async_session_factory is None")

        # 4. Synchroniser la base de données avec la configuration YAML
        logger.debug("Synchronising configuration to database")
        await _sync_config_to_db(
            loaded, notifications=app.config.get("Shiparr_NOTIFICATIONS")
        )

        # 5. Initialiser et démarrer le Scheduler
        from .deployer import Deployer
        from .scheduler import DeploymentScheduler

        async def run_deploy(repo_id: int) -> None:
            """Task exécutée par le scheduler pour chaque repo."""
            if database.async_session_factory:
                async with database.async_session_factory() as session:
                    notifications = app.config.get("Shiparr_NOTIFICATIONS")
                    deployer = Deployer(session=session, notifications=notifications)
                    await deployer.deploy(repo_id)

        scheduler = DeploymentScheduler(deploy_callable=run_deploy)
        app.config["Shiparr_SCHEDULER"] = scheduler
        scheduler.start()

        # Planifier les repositories existants
        if database.async_session_factory:
            async with database.async_session_factory() as session:
                result = await session.execute(select(Repository))
                repos = result.scalars().all()
                scheduler.reschedule_all(repos)

        # 6. Config Watcher (Polling)
        if not settings.disable_config_autoreload:
            # On ajoute une tâche périodique (toutes les 10s) pour recharger la config si changée
            async def check_config_changes() -> None:
                try:
                    # Utiliser une nouvelle instance pour ne pas garder de cache
                    new_loader = ConfigLoader(settings=settings)
                    # Pour faire simple ici: on recharge tout à chaque fois et on compare
                    # Optimisation possible: vérifier mtime avant de load()
                    # Mais ConfigLoader n'expose pas les mtimes.
                    # On va le faire "brutalement" pour l'instant: recharger et resync.

                    # Note: Idéalement, ConfigLoader devrait avoir une méthode `has_changes()`
                    # Pour l'instant, on recharge et syncDB s'occupe de ne rien faire si rien n'a changé
                    # sauf que syncDB ne checke pas si la config en RAM a changé vs config chargée.

                    # V2 Améliorée:
                    # On recharge et on laisse _sync_config_to_db logger s'il y a des changements.
                    reloaded = new_loader.load()

                    # On met à jour l'objet config global
                    app.config["Shiparr_CONFIG"] = reloaded

                    # On resynchronise la DB
                    # _sync_config_to_db est assez intelligent pour ne faire des UPDATE que si
                    # nécessaire et loggera "Updating repository..." si changement.
                    await _sync_config_to_db(
                        reloaded, notifications=app.config.get("Shiparr_NOTIFICATIONS")
                    )

                    # Si des repos ont changé, il faut aussi replanifier le scheduler (ex:
                    # interval changé)
                    if database.async_session_factory:
                        async with database.async_session_factory() as session:
                            result = await session.execute(select(Repository))
                            repos = result.scalars().all()
                            # reschedule_all est idempotent (remplace les jobs)
                            scheduler.reschedule_all(repos)

                except Exception as e:
                    logger.error(f"Config reload failed: {e}")

            # Ajouter le job de reload au scheduler
            scheduler.scheduler.add_job(
                check_config_changes,
                trigger="interval",
                seconds=10,
                id="config_reloader",
                replace_existing=True,
            )
            logger.info("Config auto-reload enabled (check every 10s)")
        else:
             logger.info("Config auto-reload DISABLED via settings")

    @app.after_serving
    async def shutdown() -> None:  # type: ignore[override]
        # Stopper le scheduler
        scheduler = app.config.get("Shiparr_SCHEDULER")
        if scheduler:
            logger.info("Stopping scheduler on shutdown")
            scheduler.stop()

        logger.info("Shutting down Shiparr app, disposing DB engine")
        await dispose_engine()

    # Enregistrer les blueprints
    app.register_blueprint(create_blueprint())

    return app


def main() -> None:
    # Configure logging once based on settings
    settings = Settings()
    configure_logging(settings.log_level)
    logger.info("Starting Shiparr via __main__", extra={"port": settings.port})

    app = create_app()
    # Settings already loaded above, mais on garde la source de vérité dans app.config
    app.config["Shiparr_SETTINGS"] = settings
    app.run(port=settings.port)


if __name__ == "__main__":  # pragma: no cover
    main()
