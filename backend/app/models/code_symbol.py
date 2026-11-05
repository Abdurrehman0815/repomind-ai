"""
RepoMind AI — CodeSymbol Model
"""
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.project import Project
    from app.models.file_document import FileDocument


class CodeSymbol(Base):
    """Represents an extracted AST symbol (function, class, method, interface)."""

    __tablename__ = "code_symbols"

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
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )  # function | class | method | variable | interface | type | enum

    line_start: Mapped[int] = mapped_column(Integer, nullable=False)
    line_end: Mapped[int] = mapped_column(Integer, nullable=False)
    signature: Mapped[str | None] = mapped_column(Text, nullable=True)
    docstring: Mapped[str | None] = mapped_column(Text, nullable=True)

    parent_symbol_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("code_symbols.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    project: Mapped["Project"] = relationship("Project", back_populates="symbols")
    file: Mapped["FileDocument"] = relationship("FileDocument", back_populates="symbols")
    parent: Mapped["CodeSymbol | None"] = relationship(
        "CodeSymbol",
        remote_side=[id],
        back_populates="children",
    )
    children: Mapped[list["CodeSymbol"]] = relationship(
        "CodeSymbol",
        back_populates="parent",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<CodeSymbol(id='{self.id}', name='{self.name}', kind='{self.kind}')>"
