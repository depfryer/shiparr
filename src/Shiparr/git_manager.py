"""Git operations for Shiparr.

Responsabilités (guide):
- Vérifier si un repo existe localement
- Clone initial si nécessaire
- Fetch + vérifier si nouveau commit (comparer hash)
- Pull si changement détecté
- Gérer l'authentification pour repos privés

GitPython n'est pas async, donc on utilise asyncio.to_thread.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Optional

from git import GitCommandError, Repo

# Cache pour éviter de faire plusieurs fetch() consécutifs pour le même dépôt
# lorsqu'il est référencé par plusieurs projets.
# Clé: (local_path_resolu, branch) -> (timestamp_monotonic, remote_hash)
_REMOTE_HASH_CACHE: dict[tuple[str, str], tuple[float, str]] = {}
# Petite durée de vie: assez longue pour mutualiser les checks dans une rafale
# de déploiements, mais suffisamment courte pour ne pas masquer de nouveaux
# commits entre deux cycles.
_REMOTE_HASH_TTL_SECONDS: float = 5.0


class GitError(RuntimeError):
    """Erreur générique Git."""


class GitManager:
    """Gestion des dépôts Git via GitPython avec interface async."""

    @staticmethod
    def _build_auth_url(url: str, token: Optional[str]) -> str:
        if not token:
            return url
        if url.startswith("http://") or url.startswith("https://"):
            # https://TOKEN@github.com/user/repo.git
            scheme, rest = url.split("://", 1)
            return f"{scheme}://{token}@{rest}"
        return url

    @staticmethod
    async def clone(url: str, branch: str, local_path: str | Path, token: str | None = None) -> str:
        """Clone le dépôt et retourne le hash du commit courant."""

        path = Path(local_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        auth_url = GitManager._build_auth_url(url, token)

        def _clone() -> str:
            try:
                repo = Repo.clone_from(auth_url, path, branch=branch)
                return repo.head.commit.hexsha
            except GitCommandError as exc:  # pragma: no cover - thin wrapper
                raise GitError(str(exc)) from exc

        return await asyncio.to_thread(_clone)

    @staticmethod
    async def get_local_hash(local_path: str | Path) -> str:
        """Retourne le hash local actuel."""

        path = Path(local_path)

        def _hash() -> str:
            if not path.exists():
                raise GitError(f"Repository does not exist at {path}")
            repo = Repo(path)
            return repo.head.commit.hexsha

        return await asyncio.to_thread(_hash)

    @staticmethod
    async def get_remote_hash(
        local_path: str | Path,
        branch: str,
        url: str | None = None,
        token: str | None = None,
    ) -> str:
        """Fetch et retourne le hash du commit distant pour la branche donnée.

        Optimisation: si plusieurs repositories partagent le même dépôt local
        (même ``local_path`` et même ``branch``), on ne fait qu'un seul
        ``fetch()`` toutes les quelques secondes et on réutilise le hash
        mémorisé pour les appels suivants.
        """

        path = Path(local_path).resolve()
        cache_key = (str(path), branch)

        # Vérifier si on a un hash récent en cache
        now = time.monotonic()
        cached = _REMOTE_HASH_CACHE.get(cache_key)
        if cached is not None:
            ts, cached_hash = cached
            if now - ts <= _REMOTE_HASH_TTL_SECONDS:
                return cached_hash

        def _remote_hash() -> str:
            if not path.exists():
                raise GitError(f"Repository does not exist at {path}")
            repo = Repo(path)
            origin = repo.remotes.origin

            # Si token fourni, on fetch via l'URL authentifiée SANS modifier la config
            if url and token:
                auth_url = GitManager._build_auth_url(url, token)
                # On met à jour explicitement la branche de tracking
                repo.git.fetch(auth_url, f"{branch}:refs/remotes/origin/{branch}")
            else:
                origin.fetch()

            remote_ref = origin.refs[branch]
            return remote_ref.commit.hexsha

        try:
            remote_hash = await asyncio.to_thread(_remote_hash)
        except GitCommandError as exc:  # pragma: no cover
            raise GitError(str(exc)) from exc

        # Mettre à jour le cache avec le hash fraîchement récupéré
        _REMOTE_HASH_CACHE[cache_key] = (now, remote_hash)
        return remote_hash

    @staticmethod
    async def pull(
        local_path: str | Path,
        branch: str = "main",
        url: str | None = None,
        token: str | None = None,
    ) -> str:
        """Effectue un fetch + reset --hard pour garantir l'état."""

        path = Path(local_path)

        def _pull() -> str:
            if not path.exists():
                raise GitError(f"Repository does not exist at {path}")
            repo = Repo(path)
            origin = repo.remotes.origin

            # Retry fetch
            for attempt in range(3):
                try:
                    if url and token:
                        auth_url = GitManager._build_auth_url(url, token)
                        repo.git.fetch(auth_url, f"{branch}:refs/remotes/origin/{branch}")
                    else:
                        origin.fetch()
                    break
                except GitCommandError as e:
                    if attempt == 2:
                        raise GitError(f"Fetch failed after 3 attempts: {e}") from e
                    time.sleep(2)

            # Reset hard instead of pull to avoid conflicts
            try:
                repo.git.reset("--hard", f"origin/{branch}")
                repo.git.clean("-fd")
            except GitCommandError as e:
                 raise GitError(f"Reset/Clean failed: {e}") from e
                 
            return repo.head.commit.hexsha

        try:
            return await asyncio.to_thread(_pull)
        except GitCommandError as exc:  # pragma: no cover
            raise GitError(str(exc)) from exc

    @staticmethod
    async def has_changes(
        local_path: str | Path,
        branch: str,
        url: str | None = None,
        token: str | None = None,
    ) -> bool:
        """Compare les hashes local et distant pour détecter un changement."""

        local = await GitManager.get_local_hash(local_path)
        remote = await GitManager.get_remote_hash(local_path, branch, url=url, token=token)
        return local != remote
