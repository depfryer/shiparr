# Guide de Développement

## Environnement de Développement

### Setup

```bash
# 1. Cloner
git clone ...

# 2. Venv
python -m venv .venv
source .venv/bin/activate

# 3. Dépendances
pip install -e ".[dev]"

# 4. Outils requis
# Installer sops, age, docker-cli sur votre machine hôte si ce n'est pas déjà fait.
```

### Tests

Nous utilisons `pytest` pour les tests unitaires et d'intégration.

```bash
# Lancer tous les tests
pytest -v

# Avec couverture
pytest -v --cov=Shiparr --cov-report=term-missing
```

### Structure du Code

- `src/Shiparr/` : Code source principal.
- `tests/` : Tests unitaires.
- `config/` : Fichiers de configuration exemples.

## Workflow de Contribution

Ce projet suit une méthodologie GitOps.

1. **Branching** :
   - `bugfix/nom-du-fix` pour les corrections.
   - `feature/nom-de-la-feature` pour les nouveautés.
2. **Pull Request** : Ouvrir une PR vers `main`.
3. **CI** : Les tests et le linting (`ruff`) sont exécutés automatiquement.
4. **Release** : Le merge sur `main` déclenche une release automatique (tag + build docker).

## Linting

Le projet utilise `ruff` pour le linting et le formatage.

```bash
ruff check .
ruff format .
```

