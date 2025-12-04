# Shiparr

Solution d'auto-hébergement GitOps pour Docker Compose, conçue pour l'écosystème *arr et au-delà.

Shiparr surveille vos dépôts Git contenant des fichiers `docker-compose.yml` et redéploie automatiquement vos services lors de nouveaux commits.

## Comment ça marche ?

Shiparr fonctionne comme un orchestrateur léger qui fait le pont entre vos dépôts Git et votre démon Docker local.

### 1. Architecture
- **Projets & Dépôts** : Vous organisez vos déploiements en "Projets". Chaque projet peut contenir plusieurs dépôts Git.
- **Configuration** : Tout est configuré via des fichiers YAML simples (dans `config/projects/`).
- **Base de données** : Une base SQLite locale stocke l'état des déploiements et l'historique.
- **Interface** : Une interface web légère (widgets) permet de visualiser l'état de vos services (compatible Dashy/Homepage).

### 2. Flux de déploiement
1. **Polling** : Shiparr vérifie périodiquement vos dépôts Git configurés (intervalle configurable par dépôt).
2. **Détection** : Si un nouveau commit est détecté sur la branche suivie (ou si la configuration change), une procédure de mise à jour est lancée.
3. **Mise à jour** :
   - `git pull` pour récupérer les derniers changements.
   - Décryptage optionnel des secrets avec **SOPS**.
   - `docker compose up -d --remove-orphans` pour appliquer les changements.
   - Nettoyage des images inutilisées (`docker image prune`).
4. **Notification** : Envoi de notifications (ex: Discord) sur le statut du déploiement (Succès/Échec).

### 3. Gestion des Secrets (SOPS)
Shiparr intègre nativement Mozilla SOPS. Si vous committez des fichiers chiffrés (ex: `secrets.enc.env`), Shiparr peut les déchiffrer à la volée avant le déploiement en utilisant votre clé privée (Age). Cela permet de gérer vos secrets en toute sécurité dans Git (GitOps).

## Installation & Développement

```bash
# Créer un environnement virtuel
python -m venv .venv
source .venv/bin/activate

# Installer les dépendances
pip install -e ".[dev]"

# Configuration de l'environnement
export Shiparr_CONFIG_PATH=./config/projects
export Shiparr_DATA_PATH=./data
# Optionnel : Clé pour SOPS
export SOPS_AGE_KEY_FILE=./secrets/age.key

# Lancer l'application
python -m Shiparr.app
```

## Tests

```bash
pytest -v --cov=Shiparr --cov-report=term-missing
```

## Contribution

Ce projet suit une méthodologie GitOps stricte pour le versioning et le déploiement.

### Workflow de développement
1. Créez une branche pour vos modifications :
   - Pour un correctif : `bugfix/votre-correctif`
   - Pour une fonctionnalité : `feature/votre-feature`
2. Ouvrez une Pull Request (PR) vers la branche `main`.
3. La CI (GitHub Actions) exécutera automatiquement :
   - Le linting (`ruff`)
   - Les tests unitaires (`pytest`)

### Versioning automatique
Lorsqu'une PR est fusionnée (merged) dans `main`, une nouvelle version est automatiquement tagguée :
- Branche `bugfix/*` -> Incrément **Patch** (ex: 1.0.0 -> 1.0.1)
- Branche `feature/*` -> Incrément **Minor** (ex: 1.0.0 -> 1.1.0)

Une fois le tag créé, une image Docker est construite et publiée sur GHCR avec les tags appropriés (`latest`, `vX`, `vX.Y`, `vX.Y.Z`).
