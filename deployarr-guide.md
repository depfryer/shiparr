# Shiparr - Guide Warp

## Vue d'ensemble et Architecture

---

## 1. Résumé du projet

**Nom** : Shiparr  
**Description** : Service de déploiement GitOps auto-hébergé pour Docker Compose, s'intégrant dans l'écosystème *arr  
**Langage** : Python 3.11+ avec Quart (async)  
**Base de données** : SQLite  
**Conteneurisation** : Docker avec accès au socket Docker

### Fonctionnalités principales (v1)

- Polling Git configurable par projet
- Détection de changements via hash Git (évite les pull/up inutiles)
- Déchiffrement automatique des `.env.enc` via SOPS/age
- Notifications via Shoutrrr (succès, échec)
- API REST avec Basic Auth optionnel
- Widget Dashy (endpoint JSON générique)
- Gestion multi-repos par fichier de configuration projet

### TODO (hors scope v1)

- Webhooks GitHub/GitLab/Gitea
- `docker compose build`
- Actions dangereuses (restart, stop, remove)
- Widget Dashy custom (Vue)
- Support auth providers autres que GitHub pour repos privés
- Healthchecks des containers déployés
- Forward Auth Traefik

---

## 2. Architecture

```
Shiparr/
├── src/
│   └── Shiparr/
│       ├── __init__.py
│       ├── app.py                 # Point d'entrée Quart
│       ├── config.py              # Chargement configuration
│       ├── models.py              # Modèles SQLAlchemy
│       ├── database.py            # Init SQLite
│       ├── scheduler.py           # Polling scheduler (APScheduler)
│       ├── deployer.py            # Logique déploiement
│       ├── git_manager.py         # Opérations Git
│       ├── sops_manager.py        # Déchiffrement SOPS/age
│       ├── notifications.py       # Intégration Shoutrrr
│       ├── auth.py                # Basic Auth middleware
│       └── routes/
│           ├── __init__.py
│           ├── api.py             # Routes API REST
│           ├── dashy.py           # Endpoint widget Dashy
│           └── logs.py            # Route logs containers
├── config/
│   └── projects/                  # Fichiers YAML par projet
│       └── example.yaml
├── tests/
│   ├── __init__.py
│   ├── test_git_manager.py
│   ├── test_sops_manager.py
│   ├── test_deployer.py
│   ├── test_config.py
│   ├── test_api.py
│   └── conftest.py
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
├── LICENSE
├── README.md
└── .env.example
```

---

## 3. Modèle de données

### Tables SQLite

**projects**
- id (INTEGER PRIMARY KEY)
- name (TEXT UNIQUE)
- config_file (TEXT)
- created_at (DATETIME)

**repositories**
- id (INTEGER PRIMARY KEY)
- project_id (INTEGER FK)
- name (TEXT)
- git_url (TEXT)
- branch (TEXT)
- path (TEXT)
- local_path (TEXT)
- last_commit_hash (TEXT)
- check_interval (INTEGER)
- created_at (DATETIME)

**deployments**
- id (INTEGER PRIMARY KEY)
- repository_id (INTEGER FK)
- commit_hash (TEXT)
- status (TEXT: pending/running/success/failed)
- started_at (DATETIME)
- finished_at (DATETIME)
- logs (TEXT)

---

## 4. Format de configuration

### Variables d'environnement du service (.env)

```
Shiparr_PORT=8080
Shiparr_CONFIG_PATH=/config/projects
Shiparr_DATA_PATH=/data
Shiparr_LOG_LEVEL=INFO

# SOPS/Age
SOPS_AGE_KEY_FILE=/secrets/age.key

# Auth (optionnel)
Shiparr_AUTH_ENABLED=false
Shiparr_AUTH_USERNAME=admin
Shiparr_AUTH_PASSWORD=changeme

# GitHub Token par défaut (peut être overridé par projet)
GITHUB_TOKEN=ghp_xxxx
```

### Fichier projet YAML (/config/projects/homelab.yaml)

```yaml
project: homelab
description: "Services homelab"

# Tokens par provider (optionnel, override les env vars)
tokens:
  github: ${GITHUB_TOKEN}
  # gitlab: ${GITLAB_TOKEN}  # TODO

repositories:
  media-stack:
    url: github.com/user/media-stack.git
    branch: main
    path: docker/           # Sous-dossier contenant docker-compose.yml
    local_path: /deployments/media-stack
    check_interval: 300     # Secondes
    env_file: .env.enc      # Fichier SOPS à déchiffrer
    notifications:
      success:
        - discord://webhook_id/webhook_token
      failure:
        - discord://webhook_id/webhook_token
        - telegram://token@telegram?chats=chat_id

  monitoring:
    url: github.com/user/monitoring.git
    branch: production
    path: ./
    local_path: /deployments/monitoring
    check_interval: 60
    notifications:
      failure:
        - pushover://user_key:api_token@

# Notifications globales (appliquées à tous les repos du projet)
global_notifications:
  failure:
    - email://smtp.example.com:587/?from=Shiparr@example.com&to=admin@example.com
```

---

## 5. API REST

### Endpoints

| Méthode | Route | Description |
|---------|-------|-------------|
| GET | /api/health | Healthcheck |
| GET | /api/projects | Liste des projets |
| GET | /api/projects/{name} | Détails d'un projet |
| GET | /api/projects/{name}/repositories | Liste des repos d'un projet |
| GET | /api/repositories/{id} | Détails d'un repo |
| GET | /api/repositories/{id}/deployments | Historique déploiements |
| POST | /api/repositories/{id}/deploy | Forcer un déploiement |
| GET | /api/deployments/{id} | Détails d'un déploiement |
| GET | /api/deployments/{id}/logs | Logs d'un déploiement |
| GET | /containers/{id}/logs | Logs Docker d'un container |

### Endpoint Dashy Widget

| Méthode | Route | Description |
|---------|-------|-------------|
| GET | /widget/dashy?project={name} | Widget JSON pour Dashy |

**Format réponse widget Dashy :**

```json
{
  "widgets": [
    {
      "type": "text",
      "value": "media-stack",
      "label": "Repository"
    },
    {
      "type": "text", 
      "value": "abc1234",
      "label": "Version"
    },
    {
      "type": "status",
      "value": "running",
      "label": "Status"
    },
    {
      "type": "text",
      "value": "2024-01-15 14:30:00",
      "label": "Last Deploy"
    }
  ]
}
```

---

## 6. Licence

Utiliser une licence custom basée sur AGPL-3.0 avec clause commerciale :

```
Shiparr - Custom Open Source License

Copyright (c) [YEAR] [YOUR NAME]

This software is provided under the following terms:

1. SOURCE CODE AVAILABILITY
   - The source code must remain publicly available
   - Any modifications must be published under this same license
   - Network use constitutes distribution (AGPL clause)

2. NON-COMMERCIAL USE
   - Free for personal, educational, and non-commercial use
   - Free for internal business use (not resold as a service)

3. COMMERCIAL USE RESTRICTION
   - Commercial use (selling, SaaS, reselling) requires explicit 
     written permission from the copyright holder
   - Contact: [YOUR EMAIL] for commercial licensing

4. ATTRIBUTION
   - Original attribution must be preserved
   - "Powered by Shiparr" notice required in derivative works

This license is based on AGPL-3.0 with additional commercial restrictions.
For the full AGPL-3.0 text, see: https://www.gnu.org/licenses/agpl-3.0.html
```

---

## Implémentation détaillée

---

## 7. Dépendances Python

### pyproject.toml - dependencies

```
quart>=0.19
quart-auth>=0.9
sqlalchemy[asyncio]>=2.0
aiosqlite>=0.19
apscheduler>=3.10
gitpython>=3.1
docker>=7.0
pyyaml>=6.0
python-dotenv>=1.0
httpx>=0.27
pydantic>=2.5
pydantic-settings>=2.1
structlog>=24.1
```

### pyproject.toml - dev dependencies

```
pytest>=8.0
pytest-asyncio>=0.23
pytest-cov>=4.1
ruff>=0.3
```

---

## 8. Composants principaux

### 8.1 config.py

**Responsabilités :**
- Charger les variables d'environnement via pydantic-settings
- Scanner le dossier projects/ et parser les YAML
- Valider la structure des fichiers de configuration
- Résoudre les variables ${ENV.XXX} dans les YAML
- Recharger la config à chaud (watch du dossier)

**Classes à implémenter :**
- `Settings` : Configuration globale du service (pydantic BaseSettings)
- `RepositoryConfig` : Config d'un repo (pydantic BaseModel)
- `ProjectConfig` : Config d'un projet avec liste de repos
- `ConfigLoader` : Charge et valide tous les projets

**Points d'attention :**
- Utiliser `yaml.safe_load()`
- Résolution des variables : regex `\${(\w+)}` remplacé par `os.environ.get()`
- Validation stricte des URLs Git
- Gestion des chemins relatifs/absolus pour local_path

### 8.2 database.py

**Responsabilités :**
- Initialiser SQLite async avec aiosqlite
- Créer les tables au démarrage si inexistantes
- Fournir une session factory

**Points d'attention :**
- Utiliser `async_sessionmaker` de SQLAlchemy 2.0
- Journal mode WAL pour performances
- Chemin configurable via `Shiparr_DATA_PATH`

### 8.3 models.py

**Responsabilités :**
- Définir les modèles SQLAlchemy ORM
- Relations entre tables

**Modèles :**
- `Project` : name, config_file, created_at, relationship repos
- `Repository` : tous les champs décrits en partie 1, relationship deployments
- `Deployment` : tous les champs décrits en partie 1

### 8.4 git_manager.py

**Responsabilités :**
- Vérifier si un repo existe localement
- Clone initial si nécessaire
- Fetch + vérifier si nouveau commit (comparer hash)
- Pull si changement détecté
- Gérer l'authentification pour repos privés

**Classe à implémenter :**
- `GitManager`

**Méthodes :**
- `async def clone(url, branch, local_path, token=None) -> str` : Clone et retourne le hash
- `async def get_remote_hash(local_path, branch) -> str` : Fetch et retourne hash distant
- `async def get_local_hash(local_path) -> str` : Retourne hash local actuel
- `async def pull(local_path) -> str` : Pull et retourne nouveau hash
- `async def has_changes(local_path, branch) -> bool` : Compare hashes

**Points d'attention :**
- GitPython n'est pas async, utiliser `asyncio.to_thread()`
- Format URL avec token : `https://TOKEN@github.com/user/repo.git`
- Gestion des erreurs Git (repo corrompu, network, auth)
- Ne jamais logger le token

### 8.5 sops_manager.py

**Responsabilités :**
- Déchiffrer les fichiers `.env.enc` avec SOPS/age
- Écrire le `.env` déchiffré temporairement pour docker compose

**Classe à implémenter :**
- `SopsManager`

**Méthodes :**
- `async def decrypt_file(encrypted_path, output_path) -> bool`
- `async def is_sops_file(file_path) -> bool` : Vérifie si le fichier est chiffré SOPS

**Points d'attention :**
- Exécuter `sops -d` via `asyncio.create_subprocess_exec()`
- Variable `SOPS_AGE_KEY_FILE` doit pointer vers la clé age
- Nettoyer le fichier .env déchiffré après déploiement (optionnel, selon sécurité voulue)
- Gérer les erreurs de déchiffrement proprement

### 8.6 deployer.py

**Responsabilités :**
- Orchestrer le workflow de déploiement complet
- Créer les entrées Deployment en DB
- Capturer les logs
- Déclencher les notifications

**Classe à implémenter :**
- `Deployer`

**Méthode principale :**
```
async def deploy(repository: Repository) -> Deployment:
    1. Créer Deployment(status=pending)
    2. Vérifier si changements Git (get_remote_hash vs last_commit_hash)
    3. Si pas de changement -> return (pas de notif succès)
    4. Pull le repo
    5. Si env_file configuré -> SopsManager.decrypt_file()
    6. Exécuter docker compose up -d
    7. Mettre à jour Deployment(status=success/failed, logs)
    8. Mettre à jour Repository.last_commit_hash
    9. Envoyer notifications
    10. Return Deployment
```

**Points d'attention :**
- Utiliser le SDK Docker Python pour `docker compose`
- Alternative : `asyncio.create_subprocess_exec("docker", "compose", ...)`
- Capturer stdout/stderr pour les logs
- Timeout configurable pour les opérations longues
- Le docker compose doit s'exécuter dans le bon répertoire (cwd)

### 8.7 notifications.py

**Responsabilités :**
- Envoyer des notifications via Shoutrrr
- Formater les messages selon le contexte (success/failure)

**Classe à implémenter :**
- `NotificationManager`

**Méthodes :**
- `async def notify(urls: list[str], event: str, deployment: Deployment)`
- `def format_message(event, deployment) -> str`

**Points d'attention :**
- Shoutrrr s'exécute via CLI : `shoutrrr send -u "url" -m "message"`
- Utiliser `asyncio.create_subprocess_exec()`
- Ne pas bloquer le déploiement si notification échoue
- Logger les erreurs de notification

### 8.8 scheduler.py

**Responsabilités :**
- Planifier les checks périodiques pour chaque repo
- Replanifier si config change
- Exécuter les déploiements en arrière-plan

**Utiliser APScheduler avec AsyncIOScheduler**

**Classe à implémenter :**
- `DeploymentScheduler`

**Méthodes :**
- `def start()` : Démarrer le scheduler
- `def stop()` : Arrêter proprement
- `def schedule_repository(repo_config)` : Ajouter un job
- `def reschedule_all()` : Recharger depuis config

**Points d'attention :**
- Chaque repo a son propre intervalle
- Job ID = `repo_{repository_id}` pour pouvoir reschedule
- Éviter les exécutions concurrentes du même repo (coalesce=True, max_instances=1)

### 8.9 auth.py

**Responsabilités :**
- Middleware Basic Auth optionnel
- Vérifier credentials si auth activée

**Points d'attention :**
- Utiliser `quart.auth` ou implémenter un `@app.before_request`
- Header `Authorization: Basic base64(user:pass)`
- Bypass pour /api/health (healthcheck)
- Configurable via `Shiparr_AUTH_ENABLED`

### 8.10 Routes API (routes/api.py)

Implémenter tous les endpoints décrits en partie 1.

**Points d'attention :**
- Utiliser des Blueprints Quart
- Sérialisation JSON avec pydantic
- Gestion d'erreurs cohérente (HTTPException)
- Pagination pour les listes (optionnel v1)

### 8.11 Route Dashy (routes/dashy.py)

Endpoint `/widget/dashy?project={name}`

**Points d'attention :**
- Format de réponse exact attendu par Dashy Custom Widget
- Agréger les infos de tous les repos du projet
- Status : running si dernier deploy success, stopped si failed, deploying si pending/running

### 8.12 Route Logs (routes/logs.py)

Endpoint `/containers/{id}/logs`

**Points d'attention :**
- Utiliser Docker SDK : `container.logs(tail=100)`
- Paramètre `tail` configurable via query param
- Stream optionnel (TODO)

---

## 9. Point d'entrée (app.py)

**Séquence de démarrage :**

1. Charger Settings depuis environnement
2. Initialiser la base de données
3. Charger la configuration des projets
4. Synchroniser DB avec config (créer/màj projets et repos)
5. Enregistrer les Blueprints
6. Démarrer le scheduler
7. Lancer Quart

**Shutdown propre :**
- Arrêter le scheduler
- Fermer les connexions DB
- Utiliser les signaux SIGTERM/SIGINT

---

## Docker, Tests et Checklist finale

---

## 10. Dockerfile

**Image de base :** `python:3.11-slim`

**Packages système requis :**
- git
- sops (télécharger depuis GitHub releases)
- age (télécharger depuis GitHub releases)
- docker-cli (pour docker compose)

**Important :** Le conteneur doit s'exécuter avec un utilisateur non-root (ex: 1000) disposant d'un répertoire HOME valide et accessible en écriture (ex: `/app`). Git nécessite un accès en écriture à `$HOME/.gitconfig` pour certaines opérations, même si nous ne stockons pas de credentials de manière persistante.

**Structure :**

```dockerfile
# Étapes à implémenter :
# 1. Base python:3.11-slim
# 2. Installer git, curl, ca-certificates
# 3. Télécharger et installer sops binaire
# 4. Télécharger et installer age binaire
# 5. Installer docker-cli (pas le daemon)
# 6. Créer user non-root "Shiparr" et configurer HOME=/app
# 7. Copier pyproject.toml et installer deps
# 8. Copier le code source
# 9. Définir WORKDIR, USER, EXPOSE, CMD
```

**Points d'attention :**
- Multi-stage build pour réduire la taille
- User non-root pour sécurité
- Healthcheck intégré
- Labels OCI standard

---

## 11. docker-compose.yml

**Structure pour auto-déploiement (uroboros) :**

```yaml
# Services à définir :
# - Shiparr:
#   - image: Shiparr:latest (ou build: .)
#   - volumes:
#     - /var/run/docker.sock:/var/run/docker.sock:ro
#     - ./config:/config:ro
#     - ./data:/data
#     - ./secrets/age.key:/secrets/age.key:ro
#     - /path/to/deployments:/deployments
#   - environment: (voir .env.example)
#   - ports: 8080
#   - restart: unless-stopped
#   - labels: traefik si besoin
```

**Points d'attention :**
- Socket Docker monté en read-only
- Volume pour la clé age
- Volume partagé pour les déploiements (là où seront clonés les repos)
- Network mode selon ton setup

---

## 12. Tests unitaires

### Structure des tests

```
tests/
├── conftest.py          # Fixtures partagées
├── test_config.py       # Tests ConfigLoader
├── test_git_manager.py  # Tests GitManager (mockés)
├── test_sops_manager.py # Tests SopsManager (mockés)
├── test_deployer.py     # Tests Deployer (mockés)
├── test_api.py          # Tests routes API
└── test_notifications.py # Tests NotificationManager
```

### conftest.py - Fixtures principales

**Fixtures à créer :**
- `app` : Instance Quart de test
- `client` : Client de test async
- `db_session` : Session SQLite en mémoire
- `sample_project_config` : Config YAML de test
- `mock_git_manager` : GitManager mocké
- `mock_docker` : Docker SDK mocké

### test_config.py

**Tests à implémenter :**
- `test_load_valid_yaml` : Charge un YAML valide
- `test_load_invalid_yaml` : Erreur sur YAML malformé
- `test_env_variable_resolution` : Résolution ${VAR}
- `test_missing_required_fields` : Validation des champs obligatoires
- `test_multiple_repositories` : Projet avec plusieurs repos

### test_git_manager.py

**Tests à implémenter (avec mocks) :**
- `test_clone_public_repo` : Clone sans token
- `test_clone_private_repo` : Clone avec token
- `test_get_local_hash` : Récupère le hash local
- `test_has_changes_true` : Détecte un changement
- `test_has_changes_false` : Pas de changement
- `test_pull_success` : Pull réussi

### test_sops_manager.py

**Tests à implémenter (avec mocks subprocess) :**
- `test_decrypt_success` : Déchiffrement réussi
- `test_decrypt_failure` : Erreur de déchiffrement
- `test_is_sops_file_true` : Détecte fichier SOPS
- `test_is_sops_file_false` : Fichier non chiffré

### test_deployer.py

**Tests à implémenter (avec mocks) :**
- `test_deploy_no_changes` : Pas de déploiement si hash identique
- `test_deploy_with_changes` : Déploiement complet
- `test_deploy_failure` : Gestion erreur docker compose
- `test_deploy_with_sops` : Déchiffrement avant deploy

### test_api.py

**Tests à implémenter :**
- `test_health_endpoint` : GET /api/health retourne 200
- `test_list_projects` : GET /api/projects
- `test_get_project` : GET /api/projects/{name}
- `test_get_project_not_found` : 404 si projet inexistant
- `test_trigger_deploy` : POST /api/repositories/{id}/deploy
- `test_auth_required` : 401 si auth activée sans credentials
- `test_auth_success` : 200 avec bon credentials

### test_notifications.py

**Tests à implémenter (avec mock subprocess) :**
- `test_notify_success` : Notification envoyée
- `test_notify_failure_silent` : Erreur notification ne bloque pas
- `test_format_message` : Format du message correct

---

## 13. Commandes de développement

### Setup initial

```bash
# Créer l'environnement
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Créer la structure
mkdir -p config/projects data secrets

# Générer une clé age
age-keygen -o secrets/age.key
```

### Lancer les tests

```bash
pytest -v --cov=Shiparr --cov-report=term-missing
```

### Lancer en dev

```bash
export Shiparr_CONFIG_PATH=./config/projects
export Shiparr_DATA_PATH=./data
export SOPS_AGE_KEY_FILE=./secrets/age.key
python -m Shiparr
```

### Build Docker

```bash
docker build -t Shiparr:latest .
```

### Test Docker local

```bash
docker compose up -d
docker compose logs -f Shiparr
```

---

## 14. Checklist de validation

### Fonctionnel

- [ ] Le service démarre sans erreur
- [ ] La config YAML est chargée correctement
- [ ] Les variables ${ENV} sont résolues
- [ ] Le scheduler planifie les jobs
- [ ] Un repo sans changement ne déclenche pas de deploy
- [ ] Un repo avec changement déclenche git pull + docker compose up
- [ ] Les fichiers .env.enc sont déchiffrés
- [ ] Les notifications sont envoyées (succès/échec)
- [ ] L'API répond correctement
- [ ] Le widget Dashy retourne le bon format
- [ ] Les logs containers sont accessibles
- [ ] L'auth Basic fonctionne quand activée

### Auto-déploiement (Uroboros)

- [ ] Shiparr peut se déployer lui-même
- [ ] Un push sur le repo Shiparr déclenche sa mise à jour
- [ ] Le service redémarre proprement après update

### Tests

- [ ] Tous les tests passent
- [ ] Coverage > 80%

### Docker

- [ ] L'image build sans erreur
- [ ] Le container démarre
- [ ] Le socket Docker est accessible
- [ ] SOPS/age fonctionnent dans le container

---

## 15. Configuration Dashy

### Intégration widget

Dans la config Dashy, ajouter :

```yaml
sections:
  - name: Deployments
    widgets:
      - type: custom
        options:
          url: http://Shiparr:8080/widget/dashy?project=homelab
```

---

## 16. TODO - Évolutions futures

### Priorité haute
- [ ] Webhooks GitHub/GitLab (endpoint POST /webhook/{provider})
- [ ] `docker compose build` avant `up`
- [ ] Support GitLab/Gitea tokens

### Priorité moyenne
- [ ] Healthchecks containers (status running/healthy/unhealthy)
- [ ] Widget Dashy custom Vue
- [ ] Rollback manuel via API
- [ ] UI web minimale

### Priorité basse
- [ ] Forward Auth Traefik
- [ ] Actions dangereuses (stop, remove, restart)
- [ ] Multi-host (SSH/TCP socket)
- [ ] Métriques Prometheus

---

## 17. Fichiers à créer - Récapitulatif

```
Shiparr/
├── src/Shiparr/
│   ├── __init__.py
│   ├── app.py
│   ├── config.py
│   ├── models.py
│   ├── database.py
│   ├── scheduler.py
│   ├── deployer.py
│   ├── git_manager.py
│   ├── sops_manager.py
│   ├── notifications.py
│   ├── auth.py
│   └── routes/
│       ├── __init__.py
│       ├── api.py
│       ├── dashy.py
│       └── logs.py
├── config/projects/.gitkeep
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_config.py
│   ├── test_git_manager.py
│   ├── test_sops_manager.py
│   ├── test_deployer.py
│   ├── test_api.py
│   └── test_notifications.py
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
├── LICENSE
├── README.md
└── .env.example
```

---

## 18. Ordre d'implémentation recommandé

1. **pyproject.toml** - Structure projet
2. **config.py** - Chargement configuration
3. **database.py + models.py** - Persistance
4. **git_manager.py** - Opérations Git
5. **sops_manager.py** - Déchiffrement
6. **deployer.py** - Logique métier
7. **notifications.py** - Shoutrrr
8. **scheduler.py** - Polling
9. **auth.py** - Basic Auth
10. **routes/** - API REST
11. **app.py** - Assemblage
12. **Tests** - Validation
13. **Dockerfile + compose** - Containerisation

---

