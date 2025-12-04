from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select

from Shiparr import database
from Shiparr.database import dispose_engine, get_database_url, get_session, init_db


def test_get_database_url_creates_parent(tmp_path: Path) -> None:
    db_path = tmp_path / "sub" / "test.db"
    url = get_database_url(db_path)
    assert "sqlite+aiosqlite" in url
    assert db_path.parent.exists()


@pytest.mark.asyncio
async def test_database_lifecycle(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"

    await init_db(db_path)
    assert database.async_engine is not None
    assert database.async_session_factory is not None

    # Simple smoke test that a session can be acquired and a trivial query executed
    async for session in get_session():
        result = await session.execute(select(1))
        assert result.scalar_one() == 1

    await dispose_engine()
    assert database.async_engine is None
