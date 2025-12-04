# Installation

## Pré-requis

- Docker et Docker Compose installés sur la machine hôte.
- Python 3.11+ (pour l'installation locale sans Docker).
- Accès au socket Docker (`/var/run/docker.sock`).

## Installation via Docker (Recommandé)

Shiparr est conçu pour être déployé via Docker. Voici un exemple de configuration `docker-compose.yml` :

```yaml
services:
  shiparr:
    image: shiparr:latest  # Ou build: .
    container_name: shiparr
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro  # Accès au socket Docker
      - ./config:/config:ro                             # Configuration des projets
      - ./data:/data                                    # Base de données SQLite
      - ./secrets/age.key:/secrets/age.key:ro           # Clé de déchiffrement SOPS (optionnel)
      - /path/to/deployments:/deployments               # Dossier où seront clonés les repos
    environment:
      - Shiparr_CONFIG_PATH=/config/projects
      - Shiparr_DATA_PATH=/data
      - SOPS_AGE_KEY_FILE=/secrets/age.key
      - TZ=Europe/Paris
    ports:
      - 8080:8080
    restart: unless-stopped
```

### Structure des dossiers recommandée

```
/opt/shiparr/
├── docker-compose.yml
├── config/
│   └── projects/
│       └── mon-projet.yaml
├── data/
│   └── Shiparr.db (créé automatiquement)
└── secrets/
    └── age.key
```

## Installation Locale (Développement)

Pour installer Shiparr directement sur votre machine :

1. **Cloner le dépôt** :
   ```bash
   git clone https://github.com/votre-user/shiparr.git
   cd shiparr
   ```

2. **Créer un environnement virtuel** :
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```

3. **Installer les dépendances** :
   ```bash
   pip install -e ".[dev]"
   ```

4. **Configuration de l'environnement** :
   ```bash
   export Shiparr_CONFIG_PATH=./config/projects
   export Shiparr_DATA_PATH=./data
   # Optionnel : Clé pour SOPS
   export SOPS_AGE_KEY_FILE=./secrets/age.key
   ```

5. **Lancer l'application** :
   ```bash
   python -m Shiparr.app
   ```

