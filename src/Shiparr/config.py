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
from pydantic import BaseModel, ConfigDict, Field, validator, model_validator
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
    enable_image_prune: bool = Field(
        default=False,
        description="Execute docker image prune -f after successful deployment.",
    )
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
    model_config = ConfigDict(extra="forbid")

    name: str

    @validator("name")
    def _validate_name_chars(cls, v: str) -> str:
        if not re.match(r"^[a-zA-Z0-9_-]+$", v):
            raise ValueError("Repository name must contain only alphanumeric characters, underscores, or hyphens.")
        return v
    url: str
    branch: str = "main"
    path: str = "./"  # Sous-dossier contenant docker-compose.yml
    local_path: str | None = None
    tokens_github: str | None = None  # Token GitHub spécifique au repo
    check_interval: int = 300
    priority: int = 0
    depends_on: list[str] = Field(default_factory=list)
    env_file: str | None = None

    @model_validator(mode="after")
    def _set_default_local_path(self) -> RepositoryConfig:
        """Définit le local_path par défaut si non fourni."""
        if not self.local_path:
            # Par défaut : /app/deployments/{name}
            # Cela correspond au volume monté dans docker-compose.yml
            self.local_path = f"/app/deployments/{self.name}"
        return self
    
    # Healthchecks
    healthcheck_url: str | None = None
    healthcheck_timeout: int = 60
    healthcheck_expected_status: int = 200

    notifications: Dict[str, list[str]] | None = None

    @validator("path")
    def _validate_path_traversal(cls, v: str) -> str:
        """Vérifie que le path ne sort pas du dossier racine (pas de traversal)."""
        if v is None:
            return v
            
        p = Path(v)
        if p.is_absolute():
             raise ValueError("Le chemin 'path' doit être relatif.")
             
        # Vérification logique du traversal
        dummy_root = Path("/dummy_root")
        try:
            resolved = (dummy_root / v).resolve()
            # .is_relative_to requires Python 3.9+
            if not resolved.is_relative_to(dummy_root):
                raise ValueError(f"Path traversal detected: {v}")
        except Exception as e:
            # Si resolve échoue ou autre
            raise ValueError(f"Invalid path: {v}") from e
            
        return v


class ProjectConfig(BaseModel):
    """Configuration d'un projet Shiparr (ensemble de repositories)."""
    model_config = ConfigDict(extra="forbid")

    project: str

    @validator("project")
    def _validate_project_name_chars(cls, v: str) -> str:
        if not re.match(r"^[a-zA-Z0-9_-]+$", v):
            raise ValueError("Project name must contain only alphanumeric characters, underscores, or hyphens.")
        return v
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
        val = os.environ.get(var_name, "")
        if not val:
            logger.warning(f"Environment variable {var_name} is not set or empty")
        else:
            # On ne loggue pas la valeur pour ne pas leaker les secrets, juste qu'on l'a trouvée
            logger.debug(f"Resolved environment variable {var_name}")
        return val.strip()

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
