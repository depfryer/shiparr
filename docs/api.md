# API Reference

Shiparr expose une API REST pour consulter l'état des déploiements et interagir avec le service.

## Endpoints

### Projets & Repositories

| Méthode | Route | Description |
|---------|-------|-------------|
| `GET` | `/api/projects` | Liste tous les projets configurés. |
| `GET` | `/api/projects/{name}` | Détails d'un projet spécifique. |
| `GET` | `/api/projects/{name}/repositories` | Liste des dépôts d'un projet. |
| `GET` | `/api/repositories/{id}` | Détails d'un dépôt (état, dernier commit). |

### Déploiements

| Méthode | Route | Description |
|---------|-------|-------------|
| `GET` | `/api/repositories/{id}/deployments` | Historique des déploiements d'un dépôt. |
| `POST` | `/api/repositories/{id}/deploy` | Forcer un déploiement immédiat (manuel). |
| `GET` | `/api/deployments/{id}` | Détails d'un déploiement spécifique. |
| `GET` | `/api/deployments/{id}/logs` | Logs complets d'un déploiement. |

### Système & Logs

| Méthode | Route | Description |
|---------|-------|-------------|
| `GET` | `/api/health` | Healthcheck du service. |
| `GET` | `/containers/{id}/logs` | Récupérer les logs Docker d'un conteneur spécifique. |

### Widgets (Dashy/Homepage)

| Méthode | Route | Description |
|---------|-------|-------------|
| `GET` | `/widget/dashy?project={name}` | Retourne un JSON formaté pour un widget custom Dashy. |

**Format de réponse Dashy :**

```json
{
  "widgets": [
    {
      "type": "text",
      "value": "media-stack",
      "label": "Repository"
    },
    {
      "type": "status",
      "value": "running",
      "label": "Status"
    }
  ]
}
```

## Authentification

Si `Shiparr_AUTH_ENABLED=true`, toutes les requêtes (sauf `/api/health`) nécessitent une authentification Basic Auth.

Header : `Authorization: Basic <base64_credentials>`

