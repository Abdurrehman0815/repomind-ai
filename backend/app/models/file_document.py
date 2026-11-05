"""
RepoMind AI — FileDocument Model
"""
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.project import Project
    from app.models.code_symbol import CodeSymbol
    from app.models.code_chunk import CodeChunk
    from app.models.dependency import Dependency


class FileDocument(Base):
    """Represents a source file inside an indexed repository."""

    __tablename__ = "file_documents"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    project_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    path: Mapped[str] = mapped_column(String(1024), nullable=False)
    relative_path: Mapped[str] = mapped_column(String(1024), nullable=False, index=True)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    language: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    line_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ast_status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="pending",
    )  # pending | parsed | error | skipped

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
    project: Mapped["Project"] = relationship("Project", back_populates="files")
    symbols: Mapped[list["CodeSymbol"]] = relationship(
        "CodeSymbol",
        back_populates="file",
        cascade="all, delete-orphan",
    )
    chunks: Mapped[list["CodeChunk"]] = relationship(
        "CodeChunk",
        back_populates="file",
        cascade="all, delete-orphan",
    )
    source_dependencies: Mapped[list["Dependency"]] = relationship(
        "Dependency",
        foreign_keys="Dependency.source_file_id",
        back_populates="source_file",
        cascade="all, delete-orphan",
    )
    target_dependencies: Mapped[list["Dependency"]] = relationship(
        "Dependency",
        foreign_keys="Dependency.target_file_id",
        back_populates="target_file",
    )

    def __repr__(self) -> str:
        return f"<FileDocument(id='{self.id}', path='{self.relative_path}', lang='{self.language}')>"
