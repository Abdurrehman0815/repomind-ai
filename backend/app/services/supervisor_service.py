"""
RepoMind AI — LangGraph Supervisor Service

Implements a LangGraph supervisor that orchestrates the AI workflow for codebase chat.
"""
from __future__ import annotations

from typing import Any, List, Optional, Dict, Tuple
from uuid import UUID
import structlog

from langgraph.graph import StateGraph, END
from typing_extensions import TypedDict

from app.ai.providers.registry import get_llm_provider
from app.ai.providers.base import GenerateOptions, StreamChunk
from app.models.chat import ChatSession, ChatMessage
from app.models.project import Project
from app.repositories.chat_repository import ChatRepository
from app.repositories.project_repository import ProjectRepository
from app.services.citation_service import CitationService
from app.services.retrieval_service import RetrievalService
from app.agents.codebase_analyst_agent import CodebaseAnalystAgent
from app.agents.planner_agent import PlannerAgent
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)


class SupervisorState(TypedDict):
    """State for the LangGraph supervisor."""
    user_query: str
    project_id: str
    session_id: str
    intent: str
    retrieved_context: List[Tuple[Any, float]]
    generated_response: str
    citations: List[dict[str, Any]]
    error: Optional[str]
    stream: bool
    # For streaming response
    response_generator: Any


class SupervisorService:
    """Service for handling chat interactions using LangGraph supervision."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.chat_repo = ChatRepository(session)
        self.project_repo = ProjectRepository(session)
        self.retrieval_service = RetrievalService(session)
        self.citation_service = CitationService(session)
        self.codebase_analyst = CodebaseAnalystAgent(session)
        self.planner_agent = PlannerAgent(session)
        # Build the LangGraph
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        """Construct the LangGraph for the supervisor workflow."""
        workflow = StateGraph(SupervisorState)

        # Add nodes
        workflow.add_node("classify_intent", self._classify_intent_node)
        workflow.add_node("retrieve_context", self._retrieve_context_node)
        workflow.add_node("generate_response", self._generate_response_node)
        workflow.add_node("validate_citations", self._validate_citations_node)
        workflow.add_node("format_final_answer", self._format_final_answer_node)

        # Define the flow
        workflow.set_entry_point("classify_intent")
        workflow.add_edge("classify_intent", "retrieve_context")
        workflow.add_edge("retrieve_context", "generate_response")
        workflow.add_edge("generate_response", "validate_citations")
        workflow.add_edge("validate_citations", "format_final_answer")
        workflow.add_edge("format_final_answer", END)

        # Add error handling? We'll handle errors in each node and set error state.
        # For now, we'll let exceptions propagate and be caught by the caller.

    def _stream_analysis_result(self, analysis_result: dict, analysis_type: str):
        """Stream an analysis result as chunks for streaming responses."""
        # Create an async iterator that yields the analysis result as chunks
        async def analysis_stream():
            # First chunk: the main answer content
            answer_content = analysis_result.get("answer", "")
            if answer_content:
                yield StreamChunk(
                    content=answer_content,
                    is_final=False
                )

            # Second chunk: metadata and completion signal
            metadata = analysis_result.get("metadata", {})
            confidence = analysis_result.get("confidence", "unknown")
            sources_count = len(analysis_result.get("sources", []))

            completion_content = f"\n\n*Analysis completed with {confidence} confidence based on {sources_count} source references.*"
            yield StreamChunk(
                content=completion_content,
                is_final=True
            )

        return analysis_stream()

        return workflow.compile()

    async def _classify_intent_node(self, state: SupervisorState) -> Dict[str, Any]:
        """Classify the user's intent."""
        try:
            intent = await self._classify_intent(state["user_query"])
            return {"intent": intent}
        except Exception as exc:
            logger.error("intent_classification_failed", error=str(exc))
            return {"error": f"Intent classification failed: {str(exc)}"}

    async def _retrieve_context_node(self, state: SupervisorState) -> Dict[str, Any]:
        """Retrieve relevant context from the codebase."""
        if state.get("error"):
            return {}  # Skip if error already occurred
        try:
            # Use specialized agents for specific intents
            if state["intent"] == "architecture_explanation":
                analysis_result = await self.codebase_analyst.analyze_architecture(
                    project_id=state["project_id"],
                    query=state["user_query"],
                    session_id=state["session_id"]
                )
                # For architecture analysis, we still want to return context for the rest of the pipeline
                # but we'll store the analysis results in the state for later use
                return {
                    "retrieved_context": [],  # We'll get context from the analysis if needed
                    "architecture_analysis": analysis_result
                }
            elif state["intent"] == "code_navigation":
                analysis_result = await self.codebase_analyst.analyze_code_navigation(
                    project_id=state["project_id"],
                    query=state["user_query"],
                    session_id=state["session_id"]
                )
                return {
                    "retrieved_context": [],  # We'll get context from the analysis if needed
                    "code_navigation_analysis": analysis_result
                }
            elif state["intent"] == "implementation_plan":
                analysis_result = await self.planner_agent.create_implementation_plan(
                    project_id=state["project_id"],
                    feature_requirement=state["user_query"],
                    session_id=state["session_id"]
                )
                return {
                    "retrieved_context": [],  # We'll get context from the analysis if needed
                    "implementation_plan_analysis": analysis_result
                }
            else:
                # Use standard retrieval for other intents
                retrieved_context = await self._retrieve_context(
                    project_id=state["project_id"],
                    query=state["user_query"],
                    intent=state["intent"]
                )
                return {"retrieved_context": retrieved_context}
        except Exception as exc:
            logger.error("context_retrieval_failed", error=str(exc))
            return {"error": f"Context retrieval failed: {str(exc)}"}

    async def _generate_response_node(self, state: SupervisorState) -> Dict[str, Any]:
        """Generate a response based on the user query and retrieved context."""
        if state.get("error"):
            return {}
        try:
            # Handle analysis results from specialized agents
            if state.get("architecture_analysis"):
                analysis = state["architecture_analysis"]
                if state["stream"]:
                    # For streaming, convert the analysis to a stream
                    response_generator = self._stream_analysis_result(
                        analysis_result=analysis,
                        analysis_type="architecture_explanation"
                    )
                    return {"response_generator": response_generator}
                else:
                    return {
                        "generated_response": analysis.get("answer", ""),
                        "analysis_metadata": analysis.get("metadata", {}),
                        "analysis_type": "architecture_explanation"
                    }
            elif state.get("code_navigation_analysis"):
                analysis = state["code_navigation_analysis"]
                if state["stream"]:
                    # For streaming, convert the analysis to a stream
                    response_generator = self._stream_analysis_result(
                        analysis_result=analysis,
                        analysis_type="code_navigation"
                    )
                    return {"response_generator": response_generator}
                else:
                    return {
                        "generated_response": analysis.get("answer", ""),
                        "analysis_metadata": analysis.get("metadata", {}),
                        "analysis_type": "code_navigation"
                    }
            elif state.get("implementation_plan_analysis"):
                analysis = state["implementation_plan_analysis"]
                if state["stream"]:
                    # For streaming, convert the analysis to a stream
                    response_generator = self._stream_analysis_result(
                        analysis_result=analysis,
                        analysis_type="implementation_plan"
                    )
                    return {"response_generator": response_generator}
                else:
                    return {
                        "generated_response": analysis.get("answer", ""),
                        "analysis_metadata": analysis.get("metadata", {}),
                        "analysis_type": "implementation_plan"
                    }
            else:
                # Use standard response generation for other intents
                if state["stream"]:
                    # For streaming, we'll return an async iterator
                    response_generator = self._generate_streaming_response(
                        user_message=state["user_query"],
                        retrieved_context=state["retrieved_context"],
                        intent=state["intent"]
                    )
                    return {"response_generator": response_generator}
                else:
                    response_content = await self._generate_response(
                        user_message=state["user_query"],
                        retrieved_context=state["retrieved_context"],
                        intent=state["intent"]
                    )
                    return {"generated_response": response_content}
        except Exception as exc:
            logger.error("response_generation_failed", error=str(exc))
            return {"error": f"Response generation failed: {str(exc)}"}

    async def _validate_citations_node(self, state: SupervisorState) -> Dict[str, Any]:
        """Validate and format citations from retrieved context or analysis results."""
        if state.get("error"):
            return {}
        # Skip citation validation for streaming? We'll do it for non-streaming for now.
        if state["stream"]:
            return {}
        try:
            # If we have analysis results with existing citations, use those
            if state.get("architecture_analysis") and state["architecture_analysis"].get("sources"):
                return {"citations": state["architecture_analysis"]["sources"]}
            elif state.get("code_navigation_analysis") and state["code_navigation_analysis"].get("sources"):
                return {"citations": state["code_navigation_analysis"]["sources"]}
            elif state.get("implementation_plan_analysis") and state["implementation_plan_analysis"].get("sources"):
                return {"citations": state["implementation_plan_analysis"]["sources"]}
            else:
                # Otherwise, validate and format citations from retrieved context
                citations = await self._validate_and_format_citations(
                    retrieved_context=state["retrieved_context"],
                    project_id=state["project_id"]
                )
                return {"citations": citations}
        except Exception as exc:
            logger.error("citation_validation_failed", error=str(exc))
            return {"error": f"Citation validation failed: {str(exc)}"}

    async def _format_final_answer_node(self, state: SupervisorState) -> Dict[str, Any]:
        """Format the final answer for non-streaming responses."""
        if state.get("error"):
            return {}
        if state["stream"]:
            # For streaming, the response is handled by the generator
            return {}
        # For non-streaming responses from analysis, we may need to store the assistant message
        # The actual response content and citations are already set in generate_response and validate_citations nodes
        # We just need to return empty dict to continue the flow
        return {}

    # Helper methods that reuse existing logic from ChatService
    async def _classify_intent(self, user_message: str) -> str:
        """Classify the user's intent (same as ChatService._classify_intent)."""
        message_lower = user_message.lower()

        # Simple keyword-based intent classification
        if any(word in message_lower for word in ["where", "location", "file", "function", "class", "method"]):
            return "code_navigation"
        elif any(word in message_lower for word in ["explain", "how", "what", "why", "architecture", "flow"]):
            return "architecture_explanation"
        elif any(word in message_lower for word in ["plan", "planning", "implement", "implementation", "build", "create"]):
            return "implementation_plan"
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
        """Retrieve relevant context from the codebase (same as ChatService._retrieve_context)."""
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
        """Generate a response based on the user message and retrieved context (same as ChatService._generate_response)."""
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
        """Generate a streaming response (same as ChatService._generate_streaming_response)."""
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
        """Format retrieved context for inclusion in the LLM prompt (same as ChatService._format_context_for_llm)."""
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
                f"[File {file_id}:L{start_line}-L{end_line}]\n{content}\n"
            )

        return "\n---\n".join(formatted_chunks)

    def _get_system_prompt_for_intent(self, intent: str) -> str:
        """Get system prompt based on the classified intent (same as ChatService._get_system_prompt_for_intent)."""
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
        """Validate and format citations from retrieved context using the citation service (same as ChatService._validate_and_format_citations)."""
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

    async def process_message(
        self,
        project_id: str,
        session_id: str,
        user_message: str,
        stream: bool = False
    ) -> dict[str, Any]:
        """
        Process a user message through the LangGraph supervisor workflow.

        Workflow: START → classify → retrieve → generate → validate → answer → END

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

        # Initialize the state for the graph
        initial_state = SupervisorState(
            user_query=user_message,
            project_id=project_id,
            session_id=session_id,
            intent="",
            retrieved_context=[],
            generated_response="",
            citations=[],
            error=None,
            stream=stream,
            response_generator=None
        )

        try:
            # Run the graph
            final_state = await self.graph.ainvoke(initial_state)

            # Check if there was an error
            if final_state.get("error"):
                raise Exception(final_state["error"])

            if stream:
                # For streaming, we return the generator and let the caller handle it
                response_dict = {
                    "session_id": chat_session.id,
                    "message_id": user_chat_message.id,
                    "intent": final_state["intent"],
                    "stream": True,
                    "response_generator": final_state["response_generator"]
                }

                # Add analysis metadata if available
                if final_state.get("architecture_analysis"):
                    response_dict["analysis_metadata"] = final_state["architecture_analysis"].get("metadata", {})
                    response_dict["analysis_type"] = "architecture_explanation"
                elif final_state.get("code_navigation_analysis"):
                    response_dict["analysis_metadata"] = final_state["code_navigation_analysis"].get("metadata", {})
                    response_dict["analysis_type"] = "code_navigation"

                return response_dict
            else:
                # Non-streaming response
                # Store assistant message
                content_to_store = final_state.get("generated_response", "")
                citations_to_store = final_state.get("citations", [])

                # If we have analysis results, use their content and citations
                if final_state.get("architecture_analysis"):
                    analysis = final_state["architecture_analysis"]
                    content_to_store = analysis.get("answer", "")
                    citations_to_store = analysis.get("sources", [])
                elif final_state.get("code_navigation_analysis"):
                    analysis = final_state["code_navigation_analysis"]
                    content_to_store = analysis.get("answer", "")
                    citations_to_store = analysis.get("sources", [])
                elif final_state.get("implementation_plan_analysis"):
                    analysis = final_state["implementation_plan_analysis"]
                    content_to_store = analysis.get("answer", "")
                    citations_to_store = analysis.get("sources", [])

                assistant_chat_message = await self.chat_repo.add_message(
                    session_id=chat_session.id,
                    role="assistant",
                    content=content_to_store,
                    citations=citations_to_store
                )

                logger.info(
                    "chat_message_processed",
                    session_id=chat_session.id,
                    user_message_id=user_chat_message.id,
                    assistant_message_id=assistant_chat_message.id,
                    intent=final_state["intent"],
                    context_chunks=len(final_state.get("retrieved_context", [])),
                    citations_count=len(final_state.get("citations", []))
                )

                # Prepare response dictionary
                response_dict = {
                    "session_id": chat_session.id,
                    "message_id": user_chat_message.id,
                    "response": final_state.get("generated_response", ""),
                    "intent": final_state["intent"],
                    "citations": final_state.get("citations", []),
                    "stream": False
                }

                # Add analysis metadata if available
                if final_state.get("architecture_analysis"):
                    response_dict["analysis_metadata"] = final_state["architecture_analysis"].get("metadata", {})
                    response_dict["analysis_type"] = "architecture_explanation"
                elif final_state.get("code_navigation_analysis"):
                    response_dict["analysis_metadata"] = final_state["code_navigation_analysis"].get("metadata", {})
                    response_dict["analysis_type"] = "code_navigation"
                elif final_state.get("implementation_plan_analysis"):
                    response_dict["analysis_metadata"] = final_state["implementation_plan_analysis"].get("metadata", {})
                    response_dict["analysis_type"] = "implementation_plan"

                return response_dict

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