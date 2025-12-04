"""Quart blueprints for Shiparr API and integrations."""

from __future__ import annotations

from quart import Blueprint

from . import api, dashy, logs


def create_blueprint() -> Blueprint:
    bp = Blueprint("Shiparr", __name__)

    api.register(bp)
    dashy.register(bp)
    logs.register(bp)

    return bp
