# Shiparr - Documentation

Shiparr est une solution d'auto-hébergement GitOps pour Docker Compose, conçue pour l'écosystème *arr et au-delà.

Il surveille vos dépôts Git contenant des fichiers `docker-compose.yml` et redéploie automatiquement vos services lors de nouveaux commits.

## Fonctionnalités principales

- **GitOps** : Vos déploiements sont définis dans Git.
- **Polling Configurable** : Vérification périodique des changements (intervalle par dépôt).
- **Gestion des Secrets** : Intégration native avec Mozilla SOPS pour chiffrer vos secrets dans Git.
- **Notifications** : Support via Shoutrrr (Discord, Telegram, Email, etc.).
- **Interface Légère** : API REST et widgets compatibles Dashy/Homepage.
- **Architecture Simple** : Python (Quart), SQLite, Docker SDK.

## Comment ça marche ?

Shiparr fonctionne comme un orchestrateur léger qui fait le pont entre vos dépôts Git et votre démon Docker local.

1. **Polling** : Shiparr vérifie périodiquement vos dépôts Git.
2. **Détection** : Si un nouveau commit est détecté, une procédure de mise à jour démarre.
3. **Mise à jour** :
   - `git pull` des changements.
   - Décryptage des secrets (SOPS).
   - `docker compose up -d` (avec suppression des orphelins).
   - Nettoyage des images (`docker image prune`).
4. **Notification** : Envoi du statut du déploiement.

## Navigation

- [Installation](./installation.md) : Comment installer et lancer Shiparr.
- [Configuration](./configuration.md) : Format des fichiers de configuration et variables d'environnement.
- [Architecture](./architecture.md) : Détails techniques sur le fonctionnement interne.
- [API](./api.md) : Documentation de l'API REST.
- [Développement](./development.md) : Guide pour contribuer au projet.

