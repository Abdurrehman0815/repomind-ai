"""
RepoMind AI — Project Model
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.file_document import FileDocument
    from app.models.code_symbol import CodeSymbol
    from app.models.code_chunk import CodeChunk
    from app.models.dependency import Dependency
    from app.models.chat import ChatSession


class Project(Base):
    """Represents a code repository indexed by RepoMind AI."""

    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    path: Mapped[str] = mapped_column(String(1024), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="unindexed",
        index=True,
    )  # unindexed | indexing | indexed | error
    repository_commit: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, index=True
    )  # Git commit hash of the repository at the time of indexing
    settings: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
        default=dict,
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
        default=dict,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        server_default=func.now(),
        onupdate=datetime.utcnow,
        nullable=False,
    )

    # Relationships
    files: Mapped[list["FileDocument"]] = relationship(
        "FileDocument",
        back_populates="project",
        cascade="all, delete-orphan",
    )
    symbols: Mapped[list["CodeSymbol"]] = relationship(
        "CodeSymbol",
        back_populates="project",
        cascade="all, delete-orphan",
    )
    chunks: Mapped[list["CodeChunk"]] = relationship(
        "CodeChunk",
        back_populates="project",
        cascade="all, delete-orphan",
    )
    dependencies: Mapped[list["Dependency"]] = relationship(
        "Dependency",
        back_populates="project",
        cascade="all, delete-orphan",
    )
    chat_sessions: Mapped[list["ChatSession"]] = relationship(
        "ChatSession",
        back_populates="project",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Project(id='{self.id}', name='{self.name}', status='{self.status}', repository_commit='{self.repository_commit}')>"