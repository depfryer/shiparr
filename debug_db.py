import asyncio

from sqlalchemy import select

from src.Shiparr.database import get_session
from src.Shiparr.models import Deployment, Project, Repository


async def check_db():
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
            print(f"- {r.id}: {r.name} (Project {r.project_id}) - Last Hash: {r.last_commit_hash}")

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
