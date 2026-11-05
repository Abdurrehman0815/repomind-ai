"""
RepoMind AI — CodeChunk Model
"""
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.project import Project
    from app.models.file_document import FileDocument


class CodeChunk(Base):
    """Represents a chunk of code embedded for vector and hybrid search."""

    __tablename__ = "code_chunks"

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
    file_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("file_documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    start_line: Mapped[int] = mapped_column(Integer, nullable=False)
    end_line: Mapped[int] = mapped_column(Integer, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # 768-dimensional embedding vector (compatible with nomic-embed-text)
    embedding = mapped_column(Vector(768), nullable=True)

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

    # Relationships
    project: Mapped["Project"] = relationship("Project", back_populates="chunks")
    file: Mapped["FileDocument"] = relationship("FileDocument", back_populates="chunks")

    def __repr__(self) -> str:
        return f"<CodeChunk(id='{self.id}', file_id='{self.file_id}', lines={self.start_line}-{self.end_line})>"
