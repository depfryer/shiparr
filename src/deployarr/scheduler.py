"""Background scheduler for periodic repository checks.

Responsabilités:
- Planifier les checks périodiques pour chaque repo
- Replanifier si config change
- Exécuter les déploiements en arrière-plan
"""

from __future__ import annotations

from typing import Callable, Dict

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from .deployer import Deployer
from .models import Repository


class DeploymentScheduler:
    """Wrapper léger autour d'AsyncIOScheduler."""

    def __init__(self, *, deploy_callable: Callable[[int], None]) -> None:
        """`deploy_callable` doit être une coroutine prenant un repository_id.

        Par exemple: `lambda repo_id: deployer.deploy(repo_id)`.
        """

        self.scheduler = AsyncIOScheduler()
        self.deploy_callable = deploy_callable

    def start(self) -> None:
        self.scheduler.start()

    def stop(self) -> None:
        self.scheduler.shutdown(wait=False)

    def schedule_repository(self, repository: Repository) -> None:
        """Ajoute ou remplace un job pour un repository donné."""

        job_id = f"repo_{repository.name}"
        trigger = IntervalTrigger(seconds=repository.check_interval)

        # On utilise replace_existing=True qui fait déjà le travail de remplacement
        # si le job existe. Pas besoin de remove_job explicite qui spamme les logs.
        # (APScheduler loggera "Added job" s'il est nouveau ou remplacé)
        
        # Cependant, pour éviter de spammer "Added job" à chaque check_config,
        # on vérifie si le job existe ET si ses paramètres ont changé.
        # Pour simplifier ici : on ne reprogramme QUE si le job n'existe pas
        # ou si on veut forcer (pas implémenté ici).
        # Mais attention : si check_interval change dans la config, il faut mettre à jour.
        
        existing_job = self.scheduler.get_job(job_id)
        if existing_job:
            # Si l'intervalle est le même, on ne fait rien pour éviter le spam
            # Note: trigger.interval renvoie un timedelta
            current_interval = existing_job.trigger.interval.total_seconds()
            if current_interval == repository.check_interval:
                return

        self.scheduler.add_job(
            self.deploy_callable,
            trigger=trigger,
            id=job_id,
            args=[repository.id],
            coalesce=True,
            max_instances=1,
            replace_existing=True,
        )

    def reschedule_all(self, repositories: list[Repository]) -> None:
        """Replanifie tous les repositories à partir d'une liste."""

        for repo in repositories:
            self.schedule_repository(repo)
