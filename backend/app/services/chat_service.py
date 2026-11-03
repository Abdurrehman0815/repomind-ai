"""
RepoMind AI — Chat Service

Implements the core AI workflow for codebase chat:
START → classify → retrieve → generate → validate citations → END
"""
from __future__ import annotations

import structlog
from typing import Any, List, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.providers.registry import get_llm_provider
from app.ai.providers.base import GenerateOptions, StreamChunk
from app.repositories.chat_repository import ChatRepository
from app.repositories.project_repository import ProjectRepository
from app.services.citation_service import CitationService
from app.services.retrieval_service import RetrievalService, file_label

logger = structlog.get_logger(__name__)


class ChatService:
    """Service for handling chat interactions with the codebase."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.chat_repo = ChatRepository(session)
        self.project_repo = ProjectRepository(session)
        self.retrieval_service = RetrievalService(session)
        self.citation_service = CitationService(session)

    async def process_message(
        self,
        project_id: str,
        session_id: str,
        user_message: str,
        stream: bool = False
    ) -> dict[str, Any]:
        """
        Process a user message through the AI workflow.

        Workflow: START → classify → retrieve → generate → validate citations → END

        Args:
            project_id: ID of the project to query
            session_id: ID of the chat session
            user_message: The user's message/query
            stream: Whether to stream the response

        Returns:
            Dictionary containing the response and metadata
        """
        logger.info(
            "processing_chat_message",
            project_id=project_id,
            session_id=session_id,
            message_length=len(user_message),
            stream=stream
        )

        # Get or create chat session
        chat_session = await self.chat_repo.get_or_create_session(
            session_id=session_id,
            project_id=project_id
        )

        # Store user message
        user_chat_message = await self.chat_repo.add_message(
            session_id=chat_session.id,
            role="user",
            content=user_message
        )

        try:
            # Step 1: Classify intent (simplified for Phase 10)
            intent = await self._classify_intent(user_message)

            # Step 2: Retrieve context
            retrieved_context = await self._retrieve_context(
                project_id=project_id,
                query=user_message,
                intent=intent
            )

            # Step 3: Generate response
            if stream:
                # For streaming, we'll return an async iterator
                response_generator = self._generate_streaming_response(
                    user_message=user_message,
                    retrieved_context=retrieved_context,
                    intent=intent
                )

                # Return early for streaming - the caller will handle the stream
                return {
                    "session_id": chat_session.id,
                    "message_id": user_chat_message.id,
                    "intent": intent,
                    "stream": True,
                    "response_generator": response_generator
                }
            else:
                # Non-streaming response
                response_content = await self._generate_response(
                    user_message=user_message,
                    retrieved_context=retrieved_context,
                    intent=intent
                )

                # Step 4: Validate and format citations using citation service
                citations = await self._validate_and_format_citations(
                    retrieved_context=retrieved_context,
                    project_id=project_id
                )

                # Store assistant message
                assistant_chat_message = await self.chat_repo.add_message(
                    session_id=chat_session.id,
                    role="assistant",
                    content=response_content,
                    citations=citations
                )

                logger.info(
                    "chat_message_processed",
                    session_id=chat_session.id,
                    user_message_id=user_chat_message.id,
                    assistant_message_id=assistant_chat_message.id,
                    intent=intent,
                    context_chunks=len(retrieved_context),
                    citations_count=len(citations)
                )

                return {
                    "session_id": chat_session.id,
                    "message_id": user_chat_message.id,
                    "response": response_content,
                    "intent": intent,
                    "citations": citations,
                    "stream": False
                }

        except Exception as exc:
            logger.error(
                "chat_message_processing_failed",
                error=str(exc),
                project_id=project_id,
                session_id=session_id,
                exc_info=True
            )

            # Store error message
            error_message = await self.chat_repo.add_message(
                session_id=chat_session.id,
                role="assistant",
                content="I encountered an error while processing your request. Please try again."
            )

            raise

    async def _classify_intent(self, user_message: str) -> str:
        """
        Classify the user's intent.
        For Phase 10, we'll use a simple keyword-based approach.
        In later phases, this will be replaced with a proper classification model.
        """
        message_lower = user_message.lower()

        # Simple keyword-based intent classification
        if any(word in message_lower for word in ["where", "location", "file", "function", "class", "method"]):
            return "code_navigation"
        elif any(word in message_lower for word in ["explain", "how", "what", "why", "architecture", "flow"]):
            return "architecture_explanation"
        elif any(word in message_lower for word in ["change", "impact", "modify", "add", "remove"]):
            return "change_impact"
        elif any(word in message_lower for word in ["test", "testing", "test plan"]):
            return "test_plan"
        elif any(word in message_lower for word in ["review", "diff", "pull request", "pr"]):
            return "code_review"
        elif any(word in message_lower for word in ["debug", "error", "bug", "issue", "problem"]):
            return "debugging"
        else:
            return "general_question"

    async def _retrieve_context(
        self,
        project_id: str,
        query: str,
        intent: str
    ) -> List[Tuple[Any, float]]:
        """
        Retrieve relevant context from the codebase.
        Uses hybrid search for better results.
        """
        try:
            # Use hybrid search to get relevant chunks
            results = await self.retrieval_service.hybrid_search(
                query_text=query,
                project_id=project_id,
                limit=10,  # Get top 10 results
                vector_weight=0.7,
                text_weight=0.3
            )

            logger.info(
                "context_retrieved",
                query=query[:50],
                intent=intent,
                results_count=len(results)
            )

            return results

        except Exception as exc:
            logger.warning(
                "context_retrieval_failed",
                error=str(exc),
                query=query[:50],
                intent=intent
            )
            # Return empty list on failure - graceful degradation
            return []

    async def _generate_response(
        self,
        user_message: str,
        retrieved_context: List[Tuple[Any, float]],
        intent: str
    ) -> str:
        """
        Generate a response based on the user message and retrieved context.
        """
        # Format the context for the LLM
        context_text = self._format_context_for_llm(retrieved_context)

        # Check if we have sufficient context to answer the question
        if not retrieved_context or len(retrieved_context) == 0:
            logger.info(
                "no_context_found",
                user_message=user_message[:50],
                intent=intent
            )
            return "I could not find sufficient evidence in the codebase to answer this question."

        # Create system prompt based on intent
        system_prompt = self._get_system_prompt_for_intent(intent)

        # Create the user prompt with context
        user_prompt = f"""Based on the following codebase context, please answer the user's question.

Context from codebase:
{context_text}

User question: {user_message}

Please provide a concise, accurate answer based only on the provided context. If the context doesn't contain sufficient information to answer the question, say "I could not find sufficient evidence in the codebase to answer this question." Include specific file references and line numbers when possible."""

        # Get LLM provider and generate response
        provider = get_llm_provider()
        options = GenerateOptions(
            temperature=0.1,
            max_tokens=2048,
            system_prompt=system_prompt
        )

        try:
            response = await provider.generate(user_prompt, options)
            return response.content
        except Exception as exc:
            logger.error(
                "response_generation_failed",
                error=str(exc),
                intent=intent
            )
            return "I encountered an error while generating the response. Please try again."

    async def _generate_streaming_response(
        self,
        user_message: str,
        retrieved_context: List[Tuple[Any, float]],
        intent: str
    ):
        """
        Generate a streaming response.
        Returns an async iterator that yields response chunks.
        """
        # Format the context for the LLM
        context_text = self._format_context_for_llm(retrieved_context)

        # Check if we have sufficient context to answer the question
        if not retrieved_context or len(retrieved_context) == 0:
            logger.info(
                "no_context_found_streaming",
                user_message=user_message[:50],
                intent=intent
            )
            # Yield the no evidence message and finish
            yield StreamChunk(
                content="I could not find sufficient evidence in the codebase to answer this question.",
                is_final=True
            )
            return

        # Create system prompt based on intent
        system_prompt = self._get_system_prompt_for_intent(intent)

        # Create the user prompt with context
        user_prompt = f"""Based on the following codebase context, please answer the user's question.

Context from codebase:
{context_text}

User question: {user_message}

Please provide a concise, accurate answer based only on the provided context. If the context doesn't contain sufficient information to answer the question, say "I could not find sufficient evidence in the codebase to answer this question." Include specific file references and line numbers when possible."""

        # Get LLM provider and stream response
        provider = get_llm_provider()
        options = GenerateOptions(
            temperature=0.1,
            max_tokens=2048,
            system_prompt=system_prompt
        )

        try:
            async for chunk in provider.stream(user_prompt, options):
                yield chunk
        except Exception as exc:
            logger.error(
                "streaming_response_generation_failed",
                error=str(exc),
                intent=intent
            )
            # Yield an error chunk
            yield StreamChunk(
                content="I encountered an error while generating the response. Please try again.",
                is_final=True
            )

    def _format_context_for_llm(self, retrieved_context: List[Tuple[Any, float]]) -> str:
        """Format retrieved context for inclusion in the LLM prompt."""
        if not retrieved_context:
            return "No relevant code context found."

        formatted_chunks = []
        for i, (chunk, score) in enumerate(retrieved_context[:5]):  # Top 5 chunks
            # Assuming chunk has content, file_id, start_line, end_line attributes
            content = getattr(chunk, 'content', str(chunk))
            file_id = getattr(chunk, 'file_id', 'unknown')
            start_line = getattr(chunk, 'start_line', '?')
            end_line = getattr(chunk, 'end_line', '?')

            formatted_chunks.append(
                f"[{file_label(file_id)}:L{start_line}-L{end_line}]\n{content}\n"
            )

        return "\n---\n".join(formatted_chunks)

    def _get_system_prompt_for_intent(self, intent: str) -> str:
        """Get system prompt based on the classified intent."""
        base_prompt = """You are RepoMind AI, an agentic codebase intelligence copilot.
Your goal is to answer questions about software repositories using only the provided codebase context.
You must:
1. Answer exclusively from the retrieved repository evidence
2. Do not invent files, functions, or dependencies that are not in the context
3. Say "I could not find sufficient evidence" when appropriate
4. Separate inference from source evidence
5. Provide specific file and line citations when possible
6. Be concise but thorough in your answers"""

        intent_specific = {
            "code_navigation": "Focus on helping the user locate specific code elements like functions, classes, or files.",
            "architecture_explanation": "Focus on explaining how different parts of the system work together and the overall architecture.",
            "change_impact": "Focus on analyzing what files would be affected by a proposed change and why.",
            "test_plan": "Focus on creating comprehensive test strategies for the requested feature or component.",
            "code_review": "Focus on reviewing code changes for potential issues, bugs, or improvements.",
            "debugging": "Focus on helping diagnose issues by tracing execution paths and identifying potential root causes.",
            "general_question": "Provide a helpful, accurate answer based on the available context."
        }

        specific_instruction = intent_specific.get(intent, intent_specific["general_question"])
        return f"{base_prompt}\n\n{specific_instruction}"

    async def _validate_and_format_citations(
        self,
        retrieved_context: List[Tuple[Any, float]],
        project_id: str
    ) -> List[dict[str, Any]]:
        """
        Validate and format citations from retrieved context using the citation service.
        """
        citations = []

        # Get project path for validation
        project = await self.project_repo.get(project_id)
        project_path = project.path if project else None

        for i, (chunk, score) in enumerate(retrieved_context[:3]):  # Top 3 chunks for citations
            try:
                # Create citation using citation service
                citation_response = await self.citation_service.create_citation_from_chunk(
                    chunk=chunk,
                    project_id=project_id
                )

                # Validate citation if we have project path
                is_valid = True
                validation_reason = ""
                if project_path:
                    is_valid, validation_reason = await self.citation_service.validate_citation(
                        citation_response, project_path
                    )
                    if not is_valid:
                        logger.warning(
                            "citation_validation_failed",
                            reason=validation_reason,
                            chunk_index=i
                        )
                        # Still include citation but mark as invalid? We'll keep is_stale from citation service.

                # Convert to dictionary for storage in chat message
                citation_dict = {
                    "file_path": citation_response.file_path,
                    "start_line": citation_response.start_line,
                    "end_line": citation_response.end_line,
                    "symbol": citation_response.symbol,
                    "file_hash": citation_response.file_hash,
                    "repository_commit": citation_response.repository_commit,
                    "is_stale": citation_response.is_stale,
                    "relevance_score": float(score)  # We can add relevance score if needed
                }
                citations.append(citation_dict)

            except Exception as exc:
                logger.error(
                    "citation_creation_failed",
                    error=str(exc),
                    chunk_index=i
                )
                continue

        return citations