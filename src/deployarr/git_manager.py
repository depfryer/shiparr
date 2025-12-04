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
from pathlib import Path
from typing import Optional

from git import Repo, GitCommandError


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
    async def get_remote_hash(local_path: str | Path, branch: str) -> str:
        """Fetch et retourne le hash du commit distant pour la branche donnée."""

        path = Path(local_path)

        def _remote_hash() -> str:
            if not path.exists():
                raise GitError(f"Repository does not exist at {path}")
            repo = Repo(path)
            origin = repo.remotes.origin
            origin.fetch()
            remote_ref = origin.refs[branch]
            return remote_ref.commit.hexsha

        try:
            return await asyncio.to_thread(_remote_hash)
        except GitCommandError as exc:  # pragma: no cover
            raise GitError(str(exc)) from exc

    @staticmethod
    async def pull(local_path: str | Path) -> str:
        """Effectue un git pull et retourne le nouveau hash."""

        path = Path(local_path)

        def _pull() -> str:
            if not path.exists():
                raise GitError(f"Repository does not exist at {path}")
            repo = Repo(path)
            origin = repo.remotes.origin
            origin.pull()
            return repo.head.commit.hexsha

        try:
            return await asyncio.to_thread(_pull)
        except GitCommandError as exc:  # pragma: no cover
            raise GitError(str(exc)) from exc

    @staticmethod
    async def has_changes(local_path: str | Path, branch: str) -> bool:
        """Compare les hashes local et distant pour détecter un changement."""

        local = await GitManager.get_local_hash(local_path)
        remote = await GitManager.get_remote_hash(local_path, branch)
        return local != remote
