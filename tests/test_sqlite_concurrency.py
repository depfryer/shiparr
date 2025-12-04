import pytest
import asyncio
from pathlib import Path
from sqlalchemy import text
from Shiparr.database import init_engine, dispose_engine

@pytest.mark.asyncio
async def test_sqlite_concurrency(tmp_path: Path):
    db_path = tmp_path / "test.db"
    engine = await init_engine(db_path)
    
    # Create table
    async with engine.begin() as conn:
        await conn.execute(text("CREATE TABLE test (id INTEGER PRIMARY KEY, val INTEGER)"))
        
    async def writer(val):
        # Use engine.begin() for transaction
        async with engine.begin() as conn:
            await conn.execute(text(f"INSERT INTO test (val) VALUES ({val})"))
            # Note: asyncio.sleep won't hold the database lock in the same way synchronous sleep does in Python threads,
            # but inside an async transaction with aiosqlite, it keeps the transaction open.
            await asyncio.sleep(0.01)
            
    # Run concurrent writers
    tasks = [writer(i) for i in range(20)]
    await asyncio.gather(*tasks)
    
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT COUNT(*) FROM test"))
        count = result.scalar()
        assert count == 20
        
    await dispose_engine()
