"""Configuration loading for Shiparr.

Responsabilités (cf. guide Shiparr):
- Charger les variables d'environnement via pydantic-settings
- Scanner le dossier projects/ et parser les YAML
- Valider la structure des fichiers de configuration
- Résoudre les variables ${ENV} dans les YAML
- Recharger la config à chaud (watch du dossier) [le watch sera ajouté plus tard]
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping

import yaml
from pydantic import BaseModel, Field, validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .logging_utils import get_logger

# Regex pour les variables ${VAR}
_ENV_VAR_PATTERN = re.compile(r"\${(\w+)}")

logger = get_logger(__name__)


class Settings(BaseSettings):
    """Configuration globale du service Shiparr.

    Chargée depuis l'environnement (cf. section 4 du guide).
    """

    model_config = SettingsConfigDict(env_prefix="Shiparr_", env_file=None, extra="ignore")

    # Chemins principaux
    # Par défaut, utiliser des chemins relatifs pour éviter les problèmes de
    # permissions lors des tests ou d'exécution locale. En production,
    # Shiparr_CONFIG_PATH et Shiparr_DATA_PATH permettent d'overrider ces
    # valeurs (par exemple vers /config/projects et /data comme dans la doc).
    config_path: Path = Field(
        default=Path("./config/projects"),
        description="Chemin du dossier contenant les fichiers de configuration projets.",
    )
    data_path: Path = Field(
        default=Path("./data"),
        description="Chemin du dossier de données (SQLite, etc.).",
    )

    # Réseau / service
    port: int = Field(default=8080, description="Port HTTP du service.")
    log_level: str = Field(default="INFO", description="Niveau de log (DEBUG, INFO, ...)")

    # Authentification basique optionnelle
    auth_enabled: bool = Field(default=False, description="Active la Basic Auth si true.")
    auth_username: str = Field(default="admin", description="Username Basic Auth.")
    auth_password: str = Field(default="changeme", description="Password Basic Auth.")

    # SOPS / age
    sops_age_key_file: Path | None = Field(
        default=None, description="Chemin vers la clé age pour SOPS (SOPS_AGE_KEY_FILE)."
    )

    # Tokens globaux (peuvent être overridés par projet)
    github_token: str | None = Field(default=None, alias="GITHUB_TOKEN")

    # Options avancées
    disable_config_autoreload: bool = Field(
        default=False,
        description="Désactive le rechargement automatique des configurations YAML.",
        alias="DISABLE_CONFIG_AUTO_RELOAD",
    )

    @validator("config_path", "data_path", "sops_age_key_file", pre=True)
    def _ensure_path(cls, value: Any) -> Any:  # type: ignore[override]
        if value is None or value == "":
            return value
        return Path(value)


class RepositoryConfig(BaseModel):
    """Configuration d'un dépôt Git à déployer."""

    name: str
    url: str
    branch: str = "main"
    path: str = "./"  # Sous-dossier contenant docker-compose.yml
    local_path: str
    check_interval: int = 300
    env_file: str | None = None

    notifications: Dict[str, list[str]] | None = None


class ProjectConfig(BaseModel):
    """Configuration d'un projet Shiparr (ensemble de repositories)."""

    project: str
    description: str | None = None

    tokens: Dict[str, str] | None = None
    repositories: Dict[str, RepositoryConfig]
    global_notifications: Dict[str, list[str]] | None = Field(default=None, alias="global_notifications")

    @validator("repositories", pre=True)
    def _inject_repo_name(cls, value: Any) -> Any:  # type: ignore[override]
        """Injecte le nom du repo dans chaque RepositoryConfig.name.

        Dans le YAML, les repos sont définis sous forme de mapping :

        repositories:
          media-stack:
            url: ...
        """

        if isinstance(value, Mapping):
            new_value: Dict[str, Any] = {}
            for repo_name, cfg in value.items():
                if isinstance(cfg, Mapping):
                    cfg = {**cfg, "name": repo_name}
                new_value[repo_name] = cfg
            return new_value
        return value


@dataclass(slots=True)
class LoadedConfig:
    """Configuration complète chargée en mémoire."""

    settings: Settings
    projects: Dict[str, ProjectConfig]


def _resolve_env_variables(raw: str) -> str:
    """Remplace les variables ${VAR} par les valeurs d'environnement.

    Si la variable n'existe pas, elle est remplacée par une chaîne vide.
    """

    def _replace(match: re.Match[str]) -> str:
        var_name = match.group(1)
        return os.environ.get(var_name, "")

    return _ENV_VAR_PATTERN.sub(_replace, raw)


def _load_yaml_file(path: Path) -> Dict[str, Any]:
    """Charge un fichier YAML de manière sûre avec résolution ${ENV}.

    - Utilise yaml.safe_load
    - Fait la résolution des variables sur le texte brut avant parsing
    """

    text = path.read_text(encoding="utf-8")
    text = _resolve_env_variables(text)
    data = yaml.safe_load(text) or {}

    if not isinstance(data, dict):
        raise ValueError(f"Le fichier YAML {path} doit contenir un mapping racine.")

    return data


class ConfigLoader:
    """Charge et valide tous les projets à partir d'un dossier.

    Cette classe ne gère pas encore le rechargement à chaud (watch). Cela
    pourra être ajouté par-dessus plus tard (par exemple avec watchdog).
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()  # type: ignore[call-arg]
        self._projects: Dict[str, ProjectConfig] = {}

    @property
    def projects(self) -> Dict[str, ProjectConfig]:
        return self._projects

    def load(self) -> LoadedConfig:
        """Charge tous les fichiers YAML du dossier de config projets.

        - Parcourt `settings.config_path`
        - Charge chaque fichier `*.yaml` / `*.yml`
        - Valide la structure via ProjectConfig
        """

        config_dir = Path(self.settings.config_path)
        if not config_dir.exists() or not config_dir.is_dir():
            raise FileNotFoundError(f"Dossier de configuration introuvable: {config_dir}")

        logger.debug("Scanning project configuration directory", extra={"config_dir": str(config_dir)})
        projects: Dict[str, ProjectConfig] = {}

        for path in sorted(config_dir.glob("*.yml")) + sorted(config_dir.glob("*.yaml")):
            logger.debug("Loading project config file", extra={"path": str(path)})
            raw = _load_yaml_file(path)
            try:
                project_cfg = ProjectConfig.model_validate(raw)
            except Exception as exc:  # pragma: no cover - message propagé
                raise ValueError(f"Erreur de validation dans {path}: {exc}") from exc

            name = project_cfg.project
            if name in projects:
                raise ValueError(f"Projet en double: {name} ({path})")

            projects[name] = project_cfg
            logger.debug(
                "Loaded project configuration",
                extra={"project": name, "file": str(path)},
            )

        self._projects = projects
        logger.debug("Completed loading project configurations", extra={"project_count": len(projects)})
        return LoadedConfig(settings=self.settings, projects=projects)
