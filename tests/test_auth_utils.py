from __future__ import annotations

import base64

from Shiparr.auth import _parse_basic_auth


def test_parse_basic_auth_valid() -> None:
    token = base64.b64encode(b"user:pass").decode("ascii")
    assert _parse_basic_auth(f"Basic {token}") == ("user", "pass")


def test_parse_basic_auth_invalid_prefix() -> None:
    assert _parse_basic_auth("Bearer token") is None
