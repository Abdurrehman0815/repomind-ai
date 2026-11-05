"""
RepoMind AI — ChatSession, ChatMessage, and EvaluationFeedback Models
"""
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.project import Project


class ChatSession(Base):
    """Represents a conversation session for a project."""

    __tablename__ = "chat_sessions"

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
    title: Mapped[str] = mapped_column(String(255), nullable=False, default="New Conversation")

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
    project: Mapped["Project"] = relationship("Project", back_populates="chat_sessions")
    messages: Mapped[list["ChatMessage"]] = relationship(
        "ChatMessage",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="ChatMessage.created_at",
    )

    def __repr__(self) -> str:
        return f"<ChatSession(id='{self.id}', title='{self.title}')>"


class ChatMessage(Base):
    """Represents a message turn within a chat session."""

    __tablename__ = "chat_messages"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )  # user | assistant | system | tool

    content: Mapped[str] = mapped_column(Text, nullable=False)

    citations: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
        default=list,
    )
    reasoning_trace: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
        default=list,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    session: Mapped["ChatSession"] = relationship("ChatSession", back_populates="messages")
    feedback: Mapped[list["EvaluationFeedback"]] = relationship(
        "EvaluationFeedback",
        back_populates="message",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<ChatMessage(id='{self.id}', role='{self.role}')>"


class EvaluationFeedback(Base):
    """User or automated evaluation feedback on assistant responses."""

    __tablename__ = "evaluation_feedbacks"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    message_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("chat_messages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    rating: Mapped[int] = mapped_column(Integer, nullable=False)  # 1 (good) / -1 (poor)
    feedback_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    message: Mapped["ChatMessage"] = relationship("ChatMessage", back_populates="feedback")

    def __repr__(self) -> str:
        return f"<EvaluationFeedback(id='{self.id}', rating={self.rating})>"
