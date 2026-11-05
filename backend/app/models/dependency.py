"""
RepoMind AI — Dependency Model
"""
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text, Integer, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.project import Project
    from app.models.file_document import FileDocument


class Dependency(Base):
    """Represents an import/dependency relationship between files or external packages."""

    __tablename__ = "dependencies"

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
    source_file_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("file_documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    target_file_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("file_documents.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    target_module: Mapped[str] = mapped_column(String(512), nullable=False)
    import_statement: Mapped[str] = mapped_column(Text, nullable=False)
    symbol_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    line_number: Mapped[Integer | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    project: Mapped["Project"] = relationship("Project", back_populates="dependencies")
    source_file: Mapped["FileDocument"] = relationship(
        "FileDocument",
        foreign_keys=[source_file_id],
        back_populates="source_dependencies",
    )
    target_file: Mapped["FileDocument | None"] = relationship(
        "FileDocument",
        foreign_keys=[target_file_id],
        back_populates="target_dependencies",
    )

    def __repr__(self) -> str:
        return f"<Dependency(source='{self.source_file_id}', module='{self.target_module}')>"