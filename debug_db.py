import asyncio

from pathlib import Path
from sqlalchemy import select

from src.Shiparr.database import get_session, init_db
from src.Shiparr.models import Deployment, Project, Repository
from src.Shiparr.config import ConfigLoader, Settings
from src.Shiparr.app import _sync_config_to_db
import src.Shiparr.database as db_module


async def check_db():
    # Initialisation DB
    db_path = Path("./data/Shiparr.db")
    await init_db(db_path)
    
    # Charger la config
    settings = Settings(config_path=Path("./config/projects"))
    loader = ConfigLoader(settings=settings)
    loaded = loader.load()
    
    # Injecter la session factory dans le module database si elle n'est pas set par init_db
    # (init_db le fait via init_engine, donc ça devrait être bon)
    
    # Synchroniser
    await _sync_config_to_db(loaded)
    
    # Récupération manuelle de la session depuis le générateur async
    # pour garantir le nettoyage via aclose() dans le bloc finally.
    session_gen = get_session()
    try:
        session = await anext(session_gen)
    except StopAsyncIteration:
        raise RuntimeError("get_session() n'a retourné aucune session") from None

    try:
        print("Projects:")
        stmt = select(Project)
        result = await session.execute(stmt)
        for p in result.scalars():
            print(f"- {p.id}: {p.name}")

        print("\nRepositories:")
        stmt = select(Repository)
        result = await session.execute(stmt)
        for r in result.scalars():
            print(f"- {r.id}: {r.name} (Project {r.project_id})")
            print(f"  URL: {r.git_url}")
            print(f"  Local Path: {r.local_path}")
            print(f"  Path: {r.path}")
            token_preview = r.github_token[:4] + "..." if r.github_token else "None"
            print(f"  Token: {token_preview}")
            print(f"  Last Hash: {r.last_commit_hash}")

        print("\nDeployments:")
        stmt = select(Deployment)
        result = await session.execute(stmt)
        for d in result.scalars():
            logs_preview = d.logs[:50] if d.logs else 'None'
            print(
                f"- {d.id}: Repo {d.repository_id} - "
                f"Status: {d.status} - Logs: {logs_preview}"
            )
    finally:
        # Fermeture explicite du générateur pour déclencher le cleanup (session.close())
        await session_gen.aclose()


if __name__ == "__main__":
    asyncio.run(check_db())
