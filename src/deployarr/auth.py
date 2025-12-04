"""Basic Auth middleware for Shiparr.

Responsabilités:
- Middleware Basic Auth optionnel
- Vérifier credentials si auth activée
- Bypass pour /api/health
"""

from __future__ import annotations

import base64
from functools import wraps
from typing import Callable, Optional

from quart import Request, Response, abort, current_app, request

from .config import Settings


def _parse_basic_auth(auth_header: str) -> tuple[str, str] | None:
    if not auth_header.startswith("Basic "):
        return None
    try:
        encoded = auth_header.split(" ", 1)[1]
        decoded = base64.b64decode(encoded).decode("utf-8")
        username, password = decoded.split(":", 1)
        return username, password
    except Exception:  # pragma: no cover - parse errors
        return None


def require_basic_auth(view: Callable) -> Callable:
    """Decorator Quart pour protéger une route par Basic Auth.

    Utilise Settings pour récupérer les credentials.
    """

    @wraps(view)
    async def wrapped(*args, **kwargs):
        settings: Settings = current_app.config["Shiparr_SETTINGS"]
        if not settings.auth_enabled:
            return await view(*args, **kwargs)

        # Bypass healthcheck
        if request.path == "/api/health":
            return await view(*args, **kwargs)

        auth_header = request.headers.get("Authorization")
        creds = _parse_basic_auth(auth_header) if auth_header else None
        if not creds:
            return Response(status=401, headers={"WWW-Authenticate": "Basic realm=Shiparr"})

        username, password = creds
        if username != settings.auth_username or password != settings.auth_password:
            return Response(status=401, headers={"WWW-Authenticate": "Basic realm=Shiparr"})

        return await view(*args, **kwargs)

    return wrapped
