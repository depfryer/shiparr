"""SOPS/age integration for Shiparr.

Responsabilités:
- Déchiffrer les fichiers `.env.enc` avec SOPS/age
- Écrire le `.env` déchiffré temporairement pour docker compose
"""

from __future__ import annotations

import asyncio
from pathlib import Path


class SopsError(RuntimeError):
    """Erreur lors du déchiffrement SOPS."""


class SopsManager:
    """Gestion des fichiers chiffrés SOPS.

    Implémentation minimale basée sur la CLI `sops`.
    """

    @staticmethod
    async def decrypt_file(encrypted_path: str | Path, output_path: str | Path) -> bool:
        """Déchiffre `encrypted_path` vers `output_path`.

        Retourne True en cas de succès, False sinon.
        """

        enc = Path(encrypted_path)
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)

        proc = await asyncio.create_subprocess_exec(
            "sops",
            "-d",
            str(enc),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            raise SopsError(stderr.decode().strip())

        out.write_bytes(stdout)
        return True

    @staticmethod
    async def is_sops_file(file_path: str | Path) -> bool:
        """Détecte si un fichier est chiffré SOPS.

        Heuristique simple: présence du champ `sops` dans le YAML/JSON.
        """

        path = Path(file_path)
        if not path.exists():
            return False

        # Lecture rapide de quelques lignes
        content = path.read_text(encoding="utf-8", errors="ignore")
        return "sops:" in content or '"sops"' in content
