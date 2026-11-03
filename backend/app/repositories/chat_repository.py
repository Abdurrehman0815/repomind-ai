"""
RepoMind AI — Chat Repository

Data access layer for ChatSession and ChatMessage entities.
"""
from typing import Sequence, Optional
import structlog
from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat import ChatSession, ChatMessage, EvaluationFeedback

logger = structlog.get_logger(__name__)


class ChatRepository:
    """Data access layer for chat sessions and messages."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_session_by_id(self, session_id: str) -> Optional[ChatSession]:
        """Get a chat session by its ID."""
        result = await self.session.execute(
            select(ChatSession).where(ChatSession.id == session_id)
        )
        return result.scalar_one_or_none()

    async def get_or_create_session(
        self,
        session_id: str,
        project_id: str
    ) -> ChatSession:
        """Get an existing session or create a new one."""
        session = await self.get_session_by_id(session_id)

        if session is None:
            # Create new session
            session = ChatSession(
                id=session_id,
                project_id=project_id,
                title="New Conversation"
            )
            self.session.add(session)
            await self.session.flush()
            logger.info(
                "chat_session_created",
                session_id=session_id,
                project_id=project_id
            )
        else:
            # Update the session's updated_at timestamp
            session.updated_at = func.now()
            await self.session.flush()

        return session

    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        citations: Optional[list[dict]] = None,
        reasoning_trace: Optional[list[dict]] = None
    ) -> ChatMessage:
        """Add a message to a chat session."""
        message = ChatMessage(
            session_id=session_id,
            role=role,
            content=content,
            citations=citations or [],
            reasoning_trace=reasoning_trace or []
        )
        self.session.add(message)
        await self.session.flush()

        logger.info(
            "chat_message_added",
            message_id=message.id,
            session_id=session_id,
            role=role
        )

        return message

    async def get_session_messages(
        self,
        session_id: str,
        limit: int = 50,
        offset: int = 0
    ) -> Sequence[ChatMessage]:
        """Get messages for a chat session with pagination."""
        result = await self.session.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.asc())
            .offset(offset)
            .limit(limit)
        )
        return result.scalars().all()

    async def get_message_by_id(self, message_id: str) -> Optional[ChatMessage]:
        """Get a specific message by its ID."""
        result = await self.session.execute(
            select(ChatMessage).where(ChatMessage.id == message_id)
        )
        return result.scalar_one_or_none()

    async def update_message_citations(
        self,
        message_id: str,
        citations: list[dict]
    ) -> Optional[ChatMessage]:
        """Update the citations for a message."""
        result = await self.session.execute(
            update(ChatMessage)
            .where(ChatMessage.id == message_id)
            .values(citations=citations)
            .returning(ChatMessage)
        )
        await self.session.flush()
        return result.scalar_one_or_none()

    async def delete_session(self, session_id: str) -> bool:
        """Delete a chat session and all its messages."""
        session = await self.get_session_by_id(session_id)
        if session:
            await self.session.delete(session)
            await self.session.flush()
            logger.info("chat_session_deleted", session_id=session_id)
            return True
        return False

    async def add_feedback(
        self,
        message_id: str,
        rating: int,
        feedback_text: Optional[str] = None
    ) -> EvaluationFeedback:
        """Add feedback to a message."""
        feedback = EvaluationFeedback(
            message_id=message_id,
            rating=rating,
            feedback_text=feedback_text
        )
        self.session.add(feedback)
        await self.session.flush()

        logger.info(
            "feedback_added",
            feedback_id=feedback.id,
            message_id=message_id,
            rating=rating
        )

        return feedback