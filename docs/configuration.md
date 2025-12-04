# Configuration

Shiparr se configure via des variables d'environnement pour le service lui-même, et des fichiers YAML pour définir les projets et dépôts à surveiller.

## Variables d'Environnement

Ces variables sont définies dans le fichier `.env` ou dans votre `docker-compose.yml`.

| Variable | Description | Défaut |
|----------|-------------|--------|
| `Shiparr_PORT` | Port d'écoute du service | `8080` |
| `Shiparr_CONFIG_PATH` | Chemin vers le dossier des configurations YAML | `/config/projects` |
| `Shiparr_DATA_PATH` | Chemin vers le dossier de données (DB) | `/data` |
| `Shiparr_LOG_LEVEL` | Niveau de log (DEBUG, INFO, WARNING, ERROR) | `INFO` |
| `SOPS_AGE_KEY_FILE` | Chemin vers la clé privée Age pour SOPS | (Optionnel) |
| `Shiparr_AUTH_ENABLED` | Activer l'authentification Basic | `false` |
| `Shiparr_AUTH_USERNAME` | Nom d'utilisateur pour l'auth | `admin` |
| `Shiparr_AUTH_PASSWORD` | Mot de passe pour l'auth | `changeme` |
| `GITHUB_TOKEN` | Token GitHub par défaut (utilisable dans les YAML) | (Optionnel) |

## Configuration des Projets (YAML)

Les fichiers de configuration des projets se trouvent dans le dossier défini par `Shiparr_CONFIG_PATH`. Chaque fichier `.yaml` représente un "Projet" pouvant contenir plusieurs dépôts.

Exemple : `/config/projects/homelab.yaml`

```yaml
project: homelab
description: "Services homelab"

# Tokens par provider (optionnel, override les env vars)
tokens:
  github: ${GITHUB_TOKEN}

repositories:
  media-stack:
    url: github.com/user/media-stack.git
    branch: main
    path: docker/           # Sous-dossier contenant docker-compose.yml
    local_path: /deployments/media-stack
    check_interval: 300     # Secondes
    env_file: .env.enc      # Fichier SOPS à déchiffrer avant déploiement
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

### Détails des champs Repository

- `url`: URL Git du dépôt (HTTPS).
- `branch`: Branche à surveiller.
- `path`: Chemin relatif dans le repo où se trouve le `docker-compose.yml`.
- `local_path`: Chemin absolu dans le conteneur Shiparr où cloner le repo.
- `check_interval`: Fréquence de vérification en secondes.
- `env_file`: (Optionnel) Nom du fichier chiffré (ex: `.env.enc`) à déchiffrer avec SOPS.
- `notifications`: Configuration des notifications spécifiques au repo.

## Gestion des Secrets (SOPS)

Shiparr intègre nativement Mozilla SOPS.
Si vous configurez `env_file: .env.enc`, Shiparr tentera de déchiffrer ce fichier en utilisant la clé Age fournie dans `SOPS_AGE_KEY_FILE` avant de lancer le déploiement.

Le fichier déchiffré sera nommé `.env` (ou le nom approprié pour Docker Compose) et sera utilisé lors du `docker compose up`.

