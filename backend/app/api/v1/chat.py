"""
RepoMind AI — Chat API

Provides endpoints for codebase chat interactions.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
import structlog
import json
from typing import AsyncIterator

from app.db.session import get_db
from app.services.chat_service import ChatService

logger = structlog.get_logger(__name__)
router = APIRouter()


@router.post("", status_code=status.HTTP_200_OK)
async def chat_message(
    project_id: str = Query(..., description="Project ID"),
    session_id: str = Query(..., description="Chat session ID"),
    message: str = Query(..., description="User message"),
    stream: bool = Query(False, description="Whether to stream the response"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Send a message to the codebase chat and get a response.

    Implements the AI workflow: START → classify → retrieve → generate → validate citations → END
    """
    logger.info(
        "chat_endpoint_called",
        project_id=project_id,
        session_id=session_id,
        message_length=len(message),
        stream=stream
    )

    # Validate that project_id and session_id are provided
    if not project_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="project_id is required"
        )

    if not session_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="session_id is required"
        )

    if not message or not message.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="message cannot be empty"
        )

    # Initialize chat service
    chat_service = ChatService(db)

    try:
        # Process the message through the AI workflow
        result = await chat_service.process_message(
            project_id=project_id,
            session_id=session_id,
            user_message=message.strip(),
            stream=stream
        )

        if stream and result.get("stream"):
            # Return streaming response
            async def event_stream() -> AsyncIterator[str]:
                try:
                    async for chunk in result["response_generator"]:
                        # Format as Server-Sent Events
                        yield f"data: {json.dumps({
                            'content': chunk.content,
                            'is_final': chunk.is_final,
                            'model': chunk.model,
                            'provider': chunk.provider
                        })}\n\n"

                        if chunk.is_final:
                            yield "data: [DONE]\n\n"
                            break
                except Exception as exc:
                    logger.error("chat_streaming_error", error=str(exc))
                    yield f"data: {json.dumps({'error': str(exc)})}\n\n"
                    yield "data: [DONE]\n\n"

            return StreamingResponse(
                event_stream(),
                media_type="text/plain",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                }
            )
        else:
            # Return non-streaming response
            return {
                "session_id": result["session_id"],
                "message_id": result["message_id"],
                "response": result["response"],
                "intent": result["intent"],
                "citations": result.get("citations", []),
                "stream": False
            }

    except Exception as exc:
        logger.error(
            "chat_endpoint_error",
            error=str(exc),
            project_id=project_id,
            session_id=session_id,
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process chat message: {str(exc)}"
        )


@router.get("/history", status_code=status.HTTP_200_OK)
async def get_chat_history(
    project_id: str = Query(..., description="Project ID"),
    session_id: str = Query(..., description="Chat session ID"),
    limit: int = Query(50, ge=1, le=100, description="Maximum number of messages to return"),
    offset: int = Query(0, ge=0, description="Number of messages to skip"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Get chat history for a session.
    """
    logger.info(
        "chat_history_requested",
        project_id=project_id,
        session_id=session_id,
        limit=limit,
        offset=offset
    )

    # Initialize chat service to access repository
    chat_service = ChatService(db)

    try:
        # Get session first to validate it exists
        session = await chat_service.chat_repo.get_session_by_id(session_id)
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Chat session with ID '{session_id}' not found"
            )

        # Validate session belongs to project
        if session.project_id != project_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Session does not belong to the specified project"
            )

        # Get messages
        messages = await chat_service.chat_repo.get_session_messages(
            session_id=session_id,
            limit=limit,
            offset=offset
        )

        # Format messages for response
        formatted_messages = []
        for msg in messages:
            formatted_messages.append({
                "id": msg.id,
                "role": msg.role,
                "content": msg.content,
                "citations": msg.citations,
                "created_at": msg.created_at.isoformat() if msg.created_at else None
            })

        return {
            "session_id": session_id,
            "project_id": project_id,
            "messages": formatted_messages,
            "limit": limit,
            "offset": offset,
            "count": len(formatted_messages)
        }

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "chat_history_error",
            error=str(exc),
            project_id=project_id,
            session_id=session_id,
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve chat history: {str(exc)}"
        )