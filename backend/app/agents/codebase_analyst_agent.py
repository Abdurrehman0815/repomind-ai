"""
RepoMind AI — Codebase Analyst Agent

Implements a specialized agent for deep codebase analysis including:
- Code retrieval with advanced filtering
- Symbol analysis and extraction
- Dependency relationship analysis
- Architecture explanation and visualization
- Source-grounded answer generation
"""

from __future__ import annotations

from typing import Any, List, Dict, Tuple
import re

import structlog

from app.ai.providers.registry import get_llm_provider
from app.ai.providers.base import GenerateOptions
from app.core.config import get_settings
from app.repositories.chat_repository import ChatRepository
from app.repositories.project_repository import ProjectRepository
from app.repositories.chunk_repository import ChunkRepository
from app.repositories.symbol_repository import SymbolRepository
from app.repositories.dependency_repository import DependencyRepository
from app.services.citation_service import CitationService
from app.services.retrieval_service import RetrievalService, clip_for_prompt, file_label
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)


class CodebaseAnalystAgent:
    """
    Specialized agent for deep codebase analysis.

    Handles sophisticated analysis tasks that require:
    - Multi-step reasoning about code relationships
    - Symbol and dependency analysis
    - Architecture explanation generation
    - Deep code retrieval with context synthesis
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.chat_repo = ChatRepository(session)
        self.project_repo = ProjectRepository(session)
        self.chunk_repo = ChunkRepository(session)
        self.symbol_repo = SymbolRepository(session)
        self.dependency_repo = DependencyRepository(session)
        self.retrieval_service = RetrievalService(session)
        self.citation_service = CitationService(session)

    async def analyze_architecture(
        self,
        project_id: str,
        query: str,
        session_id: str
    ) -> Dict[str, Any]:
        """
        Perform architecture analysis for questions about system design,
        component relationships, and data flow.
        """
        logger.info(
            "starting_architecture_analysis",
            project_id=project_id,
            query=query[:50],
            session_id=session_id
        )

        try:
            # Step 1: Retrieve broad context related to the query
            retrieved_context = await self._retrieve_broad_context(
                project_id=project_id,
                query=query
            )

            if not retrieved_context:
                return {
                    "answer": "I could not find sufficient evidence in the codebase to analyze the architecture.",
                    "confidence": "low",
                    "sources": [],
                    "analysis_type": "architecture_explanation"
                }

            # Step 2: Extract key symbols and their relationships
            symbols_analysis = await self._analyze_symbol_relationships(
                project_id=project_id,
                context_chunks=[chunk for chunk, _ in retrieved_context]
            )

            # Step 3: Analyze dependencies and data flow
            dependencies_analysis = await self._analyze_dependencies(
                project_id=project_id,
                symbols=symbols_analysis.get("key_symbols", [])
            )

            # Step 4: Generate architecture explanation
            explanation = await self._generate_architecture_explanation(
                query=query,
                context=retrieved_context,
                symbols_analysis=symbols_analysis,
                dependencies_analysis=dependencies_analysis
            )

            # Step 5: Validate and format citations
            citations = await self._validate_and_format_citations(
                retrieved_context=retrieved_context,
                project_id=project_id
            )

            logger.info(
                "architecture_analysis_completed",
                project_id=project_id,
                confidence=explanation.get("confidence", "medium"),
                sources_count=len(citations)
            )

            return {
                "answer": explanation.get("explanation", ""),
                "confidence": explanation.get("confidence", "medium"),
                "sources": citations,
                "analysis_type": "architecture_explanation",
                "metadata": {
                    "symbols_analyzed": len(symbols_analysis.get("key_symbols", [])),
                    "dependencies_found": len(dependencies_analysis.get("relationships", [])),
                    "context_chunks_used": len(retrieved_context)
                }
            }

        except Exception as exc:
            logger.error(
                "architecture_analysis_failed",
                error=str(exc),
                project_id=project_id,
                exc_info=True
            )

            return {
                "answer": "I encountered an error while analyzing the architecture. Please try again.",
                "confidence": "low",
                "sources": [],
                "analysis_type": "architecture_explanation",
                "error": str(exc)
            }

    async def analyze_code_navigation(
        self,
        project_id: str,
        query: str,
        session_id: str
    ) -> Dict[str, Any]:
        """
        Perform code navigation analysis for questions about locating
        specific functions, classes, or files.
        """
        logger.info(
            "starting_code_navigation_analysis",
            project_id=project_id,
            query=query[:50],
            session_id=session_id
        )

        try:
            # Step 1: Retrieve focused context for the specific query
            retrieved_context = await self._retrieve_focused_context(
                project_id=project_id,
                query=query,
                limit=15  # Get more results for navigation queries
            )

            if not retrieved_context:
                return {
                    "answer": "I could not find the requested code elements in the codebase.",
                    "confidence": "low",
                    "sources": [],
                    "analysis_type": "code_navigation"
                }

            # Step 2: Extract and rank relevant symbols
            relevant_symbols = await self._extract_relevant_symbols(
                project_id=project_id,
                query=query,
                context_chunks=[chunk for chunk, _ in retrieved_context]
            )

            # Step 3: Generate precise location information
            locations = await self._generate_precise_locations(
                symbols=relevant_symbols,
                context_chunks=[chunk for chunk, _ in retrieved_context]
            )

            # Step 4: Generate navigation guidance
            navigation_guidance = await self._generate_navigation_guidance(
                query=query,
                locations=locations,
                context=retrieved_context
            )

            # Step 5: Validate and format citations
            citations = await self._validate_and_format_citations(
                retrieved_context=retrieved_context,
                project_id=project_id
            )

            logger.info(
                "code_navigation_analysis_completed",
                project_id=project_id,
                confidence=navigation_guidance.get("confidence", "medium"),
                sources_count=len(citations),
                locations_found=len(locations)
            )

            return {
                "answer": navigation_guidance.get("guidance", ""),
                "confidence": navigation_guidance.get("confidence", "medium"),
                "sources": citations,
                "analysis_type": "code_navigation",
                "metadata": {
                    "symbols_found": len(relevant_symbols),
                    "precise_locations": len(locations),
                    "context_chunks_used": len(retrieved_context)
                }
            }

        except Exception as exc:
            logger.error(
                "code_navigation_analysis_failed",
                error=str(exc),
                project_id=project_id,
                exc_info=True
            )

            return {
                "answer": "I encountered an error while navigating the codebase. Please try again.",
                "confidence": "low",
                "sources": [],
                "analysis_type": "code_navigation",
                "error": str(exc)
            }

    # Helper methods for analysis

    async def _retrieve_broad_context(
        self,
        project_id: str,
        query: str
    ) -> List[Tuple[Any, float]]:
        """Retrieve broad context for architecture analysis."""
        try:
            # Use hybrid search with higher limit for broader context
            results = await self.retrieval_service.hybrid_search(
                query_text=query,
                project_id=project_id,
                limit=20,  # Higher limit for architecture analysis
                vector_weight=0.6,
                text_weight=0.4
            )
            return results
        except Exception as exc:
            logger.warning("broad_context_retrieval_failed", error=str(exc))
            return []

    async def _retrieve_focused_context(
        self,
        project_id: str,
        query: str,
        limit: int = 10
    ) -> List[Tuple[Any, float]]:
        """Retrieve focused context for code navigation."""
        try:
            # Use hybrid search with focus on exact matches
            results = await self.retrieval_service.hybrid_search(
                query_text=query,
                project_id=project_id,
                limit=limit,
                vector_weight=0.7,
                text_weight=0.3
            )
            return results
        except Exception as exc:
            logger.warning("focused_context_retrieval_failed", error=str(exc))
            return []

    async def _analyze_symbol_relationships(
        self,
        project_id: str,
        context_chunks: List[Any]
    ) -> Dict[str, Any]:
        """Analyze relationships between symbols in the context."""
        try:
            # Extract symbol IDs from chunks
            symbol_ids = []
            for chunk in context_chunks:
                if hasattr(chunk, 'symbol_ids') and chunk.symbol_ids:
                    symbol_ids.extend(chunk.symbol_ids)
                elif hasattr(chunk, 'id'):
                    # Try to find symbols associated with this chunk
                    symbols = await self.symbol_repo.find_by_chunk_id(chunk.id)
                    symbol_ids.extend([s.id for s in symbols])

            # Get detailed symbol information
            symbols = []
            if symbol_ids:
                symbols = await self.symbol_repo.get_by_ids(list(set(symbol_ids)))

            # Analyze relationships
            key_symbols = []
            symbol_relationships = []

            for symbol in symbols:
                # Categorize symbol importance
                if symbol.kind in ['class', 'function', 'method', 'interface']:
                    key_symbols.append({
                        "id": str(symbol.id),
                        "name": symbol.name,
                        "kind": symbol.kind,
                        "file_id": str(symbol.file_id) if symbol.file_id else None,
                        "line_start": symbol.line_start,
                        "line_end": symbol.line_end,
                        "docstring": getattr(symbol, 'docstring', None)
                    })

                # Find relationships (simplified - in practice this would be more sophisticated)
                if hasattr(symbol, 'references') and symbol.references:
                    for ref in symbol.references:
                        symbol_relationships.append({
                            "source_symbol": symbol.name,
                            "reference_type": "uses",
                            "target_reference": ref
                        })

            return {
                "key_symbols": key_symbols,
                "symbol_relationships": symbol_relationships,
                "total_symbols_analyzed": len(symbols)
            }

        except Exception as exc:
            logger.warning("symbol_analysis_failed", error=str(exc))
            return {
                "key_symbols": [],
                "symbol_relationships": [],
                "total_symbols_analyzed": 0
            }

    async def _extract_relevant_symbols(
        self,
        project_id: str,
        query: str,
        context_chunks: List[Any]
    ) -> List[Any]:
        """Rank symbols in the retrieved files by how well they match the query."""
        query_terms = {term for term in re.findall(r"[a-z0-9_]+", query.lower()) if len(term) > 2}
        chunk_ranges: Dict[str, List[Tuple[int, int]]] = {}
        for chunk in context_chunks:
            chunk_ranges.setdefault(str(chunk.file_id), []).append((chunk.start_line, chunk.end_line))

        scored: List[Tuple[int, Any]] = []
        for file_id, ranges in chunk_ranges.items():
            try:
                symbols = await self.symbol_repo.list_by_file(file_id)
            except Exception as exc:
                logger.warning("symbol_lookup_failed", file_id=file_id, error=str(exc))
                continue
            for symbol in symbols:
                name_terms = set(re.findall(r"[a-z0-9]+", symbol.name.lower()))
                score = 3 * len(query_terms & name_terms) + (3 if symbol.name.lower() in query_terms else 0)
                if any(start <= symbol.line_end and symbol.line_start <= end for start, end in ranges):
                    score += 1  # inside retrieved evidence
                if score:
                    scored.append((score, symbol))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [symbol for _, symbol in scored[:15]]

    async def _generate_precise_locations(
        self,
        symbols: List[Any],
        context_chunks: List[Any]
    ) -> List[Dict[str, Any]]:
        """Turn symbols (or, failing that, chunks) into exact path/line locations."""
        if symbols:
            return [
                {
                    "file_path": file_label(symbol.file_id),
                    "start_line": symbol.line_start,
                    "end_line": symbol.line_end,
                    "description": f"{symbol.kind} {symbol.name}" + (f" — {symbol.signature}" if symbol.signature else ""),
                }
                for symbol in symbols
            ]
        return [
            {
                "file_path": file_label(chunk.file_id),
                "start_line": chunk.start_line,
                "end_line": chunk.end_line,
                "description": "retrieved code section",
            }
            for chunk in context_chunks[:10]
        ]

    async def _analyze_dependencies(
        self,
        project_id: str,
        symbols: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Analyze dependencies between components."""
        try:
            # Get file IDs from symbols
            file_ids = []
            for symbol in symbols:
                if symbol.get("file_id"):
                    file_ids.append(symbol["file_id"])

            # Get dependencies for these files
            dependencies = []
            if file_ids:
                # This is a simplified approach - in practice would join through chunk->file->dependency
                dependencies = await self.dependency_repo.find_by_file_ids(list(set(file_ids)))

            # Format dependency relationships
            relationships = []
            for dep in dependencies:
                relationships.append({
                    "source_file": getattr(dep, 'source_file_id', None),
                    "target_file": getattr(dep, 'target_file_id', None),
                    "dependency_type": getattr(dep, 'dependency_type', 'unknown'),
                    "is_external": getattr(dep, 'is_external', False)
                })

            return {
                "relationships": relationships,
                "external_dependencies": [r for r in relationships if r.get("is_external")],
                "internal_dependencies": [r for r in relationships if not r.get("is_external")],
                "total_dependencies": len(relationships)
            }

        except Exception as exc:
            logger.warning("dependency_analysis_failed", error=str(exc))
            return {
                "relationships": [],
                "external_dependencies": [],
                "internal_dependencies": [],
                "total_dependencies": 0
            }

    async def _generate_architecture_explanation(
        self,
        query: str,
        context: List[Tuple[Any, float]],
        symbols_analysis: Dict[str, Any],
        dependencies_analysis: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Generate architecture explanation using LLM with analyzed data."""
        try:
            # Format context for LLM
            context_text = self._format_detailed_context_for_llm(context)

            # Format symbols analysis
            symbols_text = self._format_symbols_analysis(symbols_analysis)

            # Format dependencies analysis
            deps_text = self._format_dependencies_analysis(dependencies_analysis)

            # Create system prompt for architecture explanation
            system_prompt = """You are RepoMind AI's Codebase Analyst Agent, specializing in software architecture explanation.
Your goal is to explain how different parts of a system work together based on code evidence.
You must:
1. Base your explanation exclusively on the provided code evidence
2. Do not invent components or relationships that are not in the evidence
3. Clearly separate what is evident from what is inferred
4. Provide specific file and component references
5. Explain data flow, control flow, and component interactions
6. Be concise but thorough in your architectural analysis"""

            # Create user prompt with all the analysis data
            user_prompt = f"""Based on the following codebase analysis, please explain the architecture related to the user's question.

USER QUESTION: {query}

CODE CONTEXT:
{context_text}

KEY SYMBOLS IDENTIFIED:
{symbols_text}

DEPENDENCY RELATIONSHIPS:
{deps_text}

Answer the user's question directly and concisely (under 300 words). Cover only the parts of
architecture, data flow or dependencies that the question actually asks about, and skip any
section the evidence does not support. Cite files with line numbers. If the evidence is
insufficient, say exactly what could not be determined."""

            # Get LLM provider and generate explanation
            provider = get_llm_provider()
            options = GenerateOptions(
                temperature=0.2,
                max_tokens=get_settings().answer_max_tokens,
                system_prompt=system_prompt
            )

            response = await provider.generate(user_prompt, options)

            # Determine confidence based on evidence quality
            confidence = self._assess_explanation_confidence(
                context, symbols_analysis, dependencies_analysis
            )

            return {
                "explanation": response.content,
                "confidence": confidence,
                "analysis_complete": True
            }

        except Exception as exc:
            logger.error("architecture_explanation_generation_failed", error=str(exc))
            return {
                "explanation": "I encountered an error while generating the architecture explanation.",
                "confidence": "low",
                "analysis_complete": False
            }

    async def _generate_navigation_guidance(
        self,
        query: str,
        locations: List[Dict[str, Any]],
        context: List[Tuple[Any, float]]
    ) -> Dict[str, Any]:
        """Generate code navigation guidance."""
        try:
            # Format context for LLM
            context_text = self._format_context_for_llm(context)

            # Format locations
            locations_text = self._format_locations(locations)

            # Create system prompt for code navigation
            system_prompt = """You are RepoMind AI's Codebase Analyst Agent, specializing in code navigation.
Your goal is to help users locate specific code elements in the codebase.
You must:
1. Base your guidance exclusively on the provided code evidence
2. Provide exact file paths and line numbers when available
3. Do not invent file locations that are not in the evidence
4. Be precise and actionable in your guidance
5. If the requested element is not found, state this clearly"""

            # Create user prompt
            user_prompt = f"""Based on the following codebase analysis, please help the user locate the requested code elements.

USER QUESTION: {query}

CODE CONTEXT:
{context_text}

LOCATIONS FOUND:
{locations_text}

Please provide clear guidance on where to find the requested code elements. Include:
- Exact file paths and line numbers
- Brief description of what each location contains
- Relationships between locations if relevant
- If multiple locations exist, explain the differences
- If the element was not found, state this clearly and suggest alternatives if appropriate"""

            # Get LLM provider and generate guidance
            provider = get_llm_provider()
            options = GenerateOptions(
                temperature=0.1,
                max_tokens=min(get_settings().answer_max_tokens, 500),
                system_prompt=system_prompt
            )

            response = await provider.generate(user_prompt, options)

            # Determine confidence based on evidence quality
            confidence = self._assess_navigation_confidence(locations, context)

            return {
                "guidance": response.content,
                "confidence": confidence,
                "locations_found": len(locations)
            }

        except Exception as exc:
            logger.error("navigation_guidance_generation_failed", error=str(exc))
            return {
                "guidance": "I encountered an error while generating the navigation guidance.",
                "confidence": "low",
                "locations_found": 0
            }

    # Formatting helper methods

    def _format_detailed_context_for_llm(self, context: List[Tuple[Any, float]]) -> str:
        """Format detailed context for LLM prompts."""
        if not context:
            return "No relevant code context found."

        formatted_chunks = []
        settings = get_settings()
        for i, (chunk, score) in enumerate(context[:settings.prompt_context_chunks]):
            content = clip_for_prompt(getattr(chunk, 'content', chunk))
            file_id = getattr(chunk, 'file_id', 'unknown')
            start_line = getattr(chunk, 'start_line', '?')
            end_line = getattr(chunk, 'end_line', '?')
            symbol = getattr(chunk, 'symbol', 'unknown')

            formatted_chunks.append(
                f"[{file_label(file_id)}:L{start_line}-L{end_line}] Symbol: {symbol} (Relevance: {score:.2f})\n{content}\n"
            )

        return "\n---\n".join(formatted_chunks)

    def _format_context_for_llm(self, context: List[Tuple[Any, float]]) -> str:
        """Format context for LLM prompts (simplified version)."""
        if not context:
            return "No relevant code context found."

        formatted_chunks = []
        for i, (chunk, score) in enumerate(context[:5]):  # Top 5 chunks
            content = getattr(chunk, 'content', str(chunk))
            file_id = getattr(chunk, 'file_id', 'unknown')
            start_line = getattr(chunk, 'start_line', '?')
            end_line = getattr(chunk, 'end_line', '?')

            formatted_chunks.append(
                f"[{file_label(file_id)}:L{start_line}-L{end_line}]\n{content}\n"
            )

        return "\n---\n".join(formatted_chunks)

    def _format_symbols_analysis(self, symbols_analysis: Dict[str, Any]) -> str:
        """Format symbols analysis for LLM prompts."""
        key_symbols = symbols_analysis.get("key_symbols", [])
        if not key_symbols:
            return "No key symbols identified."

        formatted = []
        for symbol in key_symbols[:10]:  # Top 10 symbols
            formatted.append(
                f"- {symbol['name']} ({symbol['kind']}) in {file_label(symbol['file_id'])}:L{symbol['line_start']}-L{symbol['line_end']}"
                f"{(': ' + symbol['docstring'][:100] + '...') if symbol.get('docstring') else ''}"
            )

        return "\n".join(formatted)

    def _format_dependencies_analysis(self, dependencies_analysis: Dict[str, Any]) -> str:
        """Format dependencies analysis for LLM prompts."""
        relationships = dependencies_analysis.get("relationships", [])
        if not relationships:
            return "No dependency relationships identified."

        formatted = []
        for rel in relationships[:10]:  # Top 10 relationships
            formatted.append(
                f"- {file_label(rel['source_file'])} → {file_label(rel['target_file'])} ({rel['dependency_type']})"
                f"{' [external]' if rel.get('is_external') else ''}"
            )

        return "\n".join(formatted)

    def _format_locations(self, locations: List[Dict[str, Any]]) -> str:
        """Format locations for LLM prompts."""
        if not locations:
            return "No specific locations identified."

        formatted = []
        for i, location in enumerate(locations[:10]):  # Top 10 locations
            location_str = (
                f"{i+1}. {location.get('file_path', 'unknown')}:L{location.get('start_line', '?')}-L{location.get('end_line', '?')}"
            )
            if location.get('description'):
                location_str += ' - ' + location.get('description', '')
            formatted.append(location_str)

        return "\n".join(formatted)

    # Confidence assessment methods

    def _assess_explanation_confidence(
        self,
        context: List[Tuple[Any, float]],
        symbols_analysis: Dict[str, Any],
        dependencies_analysis: Dict[str, Any]
    ) -> str:
        """Assess confidence level for architecture explanation."""
        context_score = min(len(context) / 10.0, 1.0)  # Normalize to 0-1
        symbols_score = min(len(symbols_analysis.get("key_symbols", [])) / 5.0, 1.0)
        deps_score = min(len(dependencies_analysis.get("relationships", [])) / 5.0, 1.0)

        avg_score = (context_score + symbols_score + deps_score) / 3.0

        if avg_score >= 0.7:
            return "high"
        elif avg_score >= 0.4:
            return "medium"
        else:
            return "low"

    def _assess_navigation_confidence(
        self,
        locations: List[Dict[str, Any]],
        context: List[Tuple[Any, float]]
    ) -> str:
        """Assess confidence level for code navigation."""
        location_score = min(len(locations) / 5.0, 1.0)  # Normalize to 0-1
        context_score = min(len(context) / 10.0, 1.0)

        avg_score = (location_score + context_score) / 2.0

        if avg_score >= 0.7:
            return "high"
        elif avg_score >= 0.4:
            return "medium"
        else:
            return "low"

    # Citation validation (reuse from supervisor service pattern)

    async def _validate_and_format_citations(
        self,
        retrieved_context: List[Tuple[Any, float]],
        project_id: str
    ) -> List[dict[str, Any]]:
        """Validate and format citations from retrieved context."""
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

                # Convert to dictionary for storage in chat message
                citation_dict = {
                    "file_path": citation_response.file_path,
                    "start_line": citation_response.start_line,
                    "end_line": citation_response.end_line,
                    "symbol": citation_response.symbol,
                    "file_hash": citation_response.file_hash,
                    "repository_commit": citation_response.repository_commit,
                    "is_stale": citation_response.is_stale,
                    "relevance_score": float(score)
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