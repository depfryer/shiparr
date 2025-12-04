# Architecture

## Vue d'ensemble

Shiparr est construit avec une architecture modulaire autour d'un scheduler central et d'une base de données SQLite.

```
Shiparr/
├── src/
│   └── Shiparr/
│       ├── app.py                 # Point d'entrée Quart
│       ├── config.py              # Chargement configuration
│       ├── models.py              # Modèles SQLAlchemy
│       ├── database.py            # Init SQLite
│       ├── scheduler.py           # Polling scheduler (APScheduler)
│       ├── deployer.py            # Logique déploiement (Docker SDK)
│       ├── git_manager.py         # Opérations Git
│       ├── sops_manager.py        # Déchiffrement SOPS/age
│       ├── notifications.py       # Intégration Shoutrrr
│       └── routes/                # API REST
```

## Composants

### 1. Scheduler & Polling
Utilise `APScheduler` pour exécuter des tâches périodiques. Chaque dépôt configuré possède son propre job de vérification.
- Vérifie le hash du commit distant (`git ls-remote`).
- Compare avec le dernier hash déployé en base de données.
- Si différent, déclenche le déploiement.

### 2. Git Manager
Gère les opérations Git :
- Clone initial.
- Pull des mises à jour.
- Gestion des credentials (tokens).

### 3. Sops Manager
Wrapper autour du binaire `sops`.
- Déchiffre les fichiers `.env.enc` en `.env` temporaires.
- Utilise les clés Age montées dans le conteneur.

### 4. Deployer
Orchestre le déploiement via le SDK Docker Python.
- Exécute `docker compose up -d --remove-orphans`.
- Capture les logs de déploiement.
- Effectue un `docker image prune` pour nettoyer.

### 5. Database (SQLite)
Stocke l'état du système :
- **Projects** : Projets configurés.
- **Repositories** : Dépôts surveillés et leur état actuel.
- **Deployments** : Historique des déploiements (succès/échec, logs, timestamp).

## Flux de Données

1. **Démarrage** : `ConfigLoader` lit les YAML -> Met à jour la DB -> `Scheduler` crée les jobs.
2. **Job (Polling)** : `GitManager` check remote hash.
3. **Détection Changement** :
   - `GitManager.pull()`
   - `SopsManager.decrypt()` (si besoin)
   - `Deployer.deploy()` -> Docker Engine
   - Mise à jour DB (Status, Logs)
   - `NotificationManager.notify()`

