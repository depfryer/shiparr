"""Container logs endpoint."""

from __future__ import annotations

from typing import Any

import docker
from quart import Blueprint, jsonify, request

from ..auth import require_basic_auth


def register(bp: Blueprint) -> None:
    bp.add_url_rule("/containers/<string:container_id>/logs", view_func=get_container_logs, methods=["GET"])


@require_basic_auth
async def get_container_logs(container_id: str) -> Any:
    client = docker.from_env()
    tail = request.args.get("tail", type=int) or 100
    container = client.containers.get(container_id)
    logs = container.logs(tail=tail).decode("utf-8", errors="ignore")
    return jsonify({"logs": logs})
