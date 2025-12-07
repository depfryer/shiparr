"""ORM models for Shiparr.

Basé sur le modèle de données du guide:
- projects
- repositories
- deployments
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    config_file: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    repositories: Mapped[list["Repository"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
    )


class Repository(Base):
    __tablename__ = "repositories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)

    name: Mapped[str] = mapped_column(String, nullable=False)
    git_url: Mapped[str] = mapped_column(String, nullable=False)
    branch: Mapped[str] = mapped_column(String, nullable=False)
    path: Mapped[str] = mapped_column(String, nullable=False)
    local_path: Mapped[str] = mapped_column(String, nullable=False)
    github_token: Mapped[str | None] = mapped_column(String, nullable=True)
    last_commit_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    check_interval: Mapped[int] = mapped_column(Integer, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    depends_on: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Healthcheck configuration
    healthcheck_url: Mapped[str | None] = mapped_column(String, nullable=True)
    healthcheck_timeout: Mapped[int] = mapped_column(Integer, default=60)
    healthcheck_expected_status: Mapped[int] = mapped_column(Integer, default=200)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    project: Mapped[Project] = relationship(back_populates="repositories")
    deployments: Mapped[list["Deployment"]] = relationship(
        back_populates="repository",
        cascade="all, delete-orphan",
    )


class Deployment(Base):
    __tablename__ = "deployments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    repository_id: Mapped[int] = mapped_column(ForeignKey("repositories.id"), nullable=False)

    commit_hash: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)  # pending/running/success/failed
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    logs: Mapped[str | None] = mapped_column(Text, nullable=True)

    repository: Mapped[Repository] = relationship(back_populates="deployments")
