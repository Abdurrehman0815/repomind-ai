"""
RepoMind AI — Change Impact Analysis Agent

Implements a specialized agent for analyzing the impact of changes on the codebase.
"""

from __future__ import annotations

from typing import Any, List, Dict, Tuple, Optional
from uuid import UUID
import structlog

from app.ai.providers.registry import get_llm_provider
from app.ai.providers.base import GenerateOptions
from app.models.chat import ChatSession, ChatMessage
from app.models.project import Project
from app.repositories.chat_repository import ChatRepository
from app.repositories.project_repository import ProjectRepository
from app.repositories.chunk_repository import ChunkRepository
from app.repositories.symbol_repository import SymbolRepository
from app.repositories.dependency_repository import DependencyRepository
from app.services.citation_service import CitationService
from app.services.retrieval_service import RetrievalService
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)


class ChangeImpactAgent:
    """
    Specialized agent for analyzing the impact of changes on the codebase.

    Handles sophisticated change impact tasks that require:
    - Understanding the proposed change or feature
    - Analyzing the existing codebase structure
    - Using dependency relationships to identify ripple effects
    - Identifying which files are likely to be affected
    - Providing evidence-based assessments
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

    async def analyze_change_impact(
        self,
        project_id: str,
        change_query: str,
        session_id: str
    ) -> Dict[str, Any]:
        """
        Analyze the impact of a proposed change on the codebase.

        Args:
            project_id: ID of the project to analyze
            change_query: Description of the change or feature (e.g., "Which files will change if I add Google login?")
            session_id: ID of the chat session

        Returns:
            Dictionary containing the change impact analysis and metadata
        """
        logger.info(
            "starting_change_impact_analysis",
            project_id=project_id,
            change_query=change_query[:50],
            session_id=session_id
        )

        try:
            # Step 1: Retrieve context related to the change query
            retrieved_context = await self._retrieve_change_context(
                project_id=project_id,
                change_query=change_query
            )

            if not retrieved_context:
                return {
                    "answer": "I could not find sufficient evidence in the codebase to analyze the impact of this change.",
                    "confidence": "low",
                    "sources": [],
                    "analysis_type": "change_impact"
                }

            # Step 2: Extract symbols and files from the context
            context_symbols, context_files = await self._extract_symbols_and_files(
                retrieved_context=retrieved_context
            )

            # Step 3: Use dependency graph to find related files
            dependency_map = await self._analyze_dependencies(
                project_id=project_id,
                file_ids=context_files
            )

            # Step 4: Identify affected files based on change type and dependencies
            affected_files_analysis = await self._identify_affected_files_for_change(
                project_id=project_id,
                change_query=change_query,
                context_symbols=context_symbols,
                context_files=context_files,
                dependency_map=dependency_map
            )

            # Step 5: Generate a summary answer and assess risk
            impact_summary = await self._generate_impact_summary(
                change_query=change_query,
                context=retrieved_context,
                affected_files_analysis=affected_files_analysis,
                dependency_map=dependency_map
            )

            # Step 6: Validate and format citations
            citations = await self._validate_and_format_citations(
                retrieved_context=retrieved_context,
                project_id=project_id
            )

            logger.info(
                "change_impact_analysis_completed",
                project_id=project_id,
                confidence=impact_summary.get("confidence", "medium"),
                sources_count=len(citations),
                affected_files_count=len(affected_files_analysis.get("affected_files", []))
            )

            return {
                "answer": impact_summary.get("summary", ""),
                "confidence": impact_summary.get("confidence", "medium"),
                "sources": citations,
                "analysis_type": "change_impact",
                "metadata": {
                    "context_chunks_used": len(retrieved_context),
                    "affected_files_count": len(affected_files_analysis.get("affected_files", [])),
                    "dependency_relationships_found": len(dependency_map.get("dependencies", [])),
                    "risk_level": impact_summary.get("risk_level", "medium")
                }
            }

        except Exception as exc:
            logger.error(
                "change_impact_analysis_failed",
                error=str(exc),
                project_id=project_id,
                exc_info=True
            )

            return {
                "answer": "I encountered an error while analyzing the change impact. Please try again.",
                "confidence": "low",
                "sources": [],
                "analysis_type": "change_impact",
                "error": str(exc)
            }

    # Helper methods for change impact analysis

    async def _retrieve_change_context(
        self,
        project_id: str,
        change_query: str
    ) -> List[Tuple[Any, float]]:
        """Retrieve context related to the change query."""
        try:
            # Use hybrid search to get relevant chunks for the change
            results = await self.retrieval_service.hybrid_search(
                query_text=change_query,
                project_id=project_id,
                limit=10,  # Get relevant results
                vector_weight=0.7,
                text_weight=0.3
            )
            return results
        except Exception as exc:
            logger.warning("change_context_retrieval_failed", error=str(exc))
            return []

    async def _extract_symbols_and_files(
        self,
        retrieved_context: List[Tuple[Any, float]]
    ) -> Tuple[List[Any], List[str]]:
        """Extract symbol IDs and file IDs from retrieved context."""
        symbol_ids = []
        file_ids = set()

        for chunk, _ in retrieved_context:
            # Extract symbol IDs
            if hasattr(chunk, 'symbol_ids') and chunk.symbol_ids:
                symbol_ids.extend(chunk.symbol_ids)
            elif hasattr(chunk, 'id'):
                # Try to find symbols associated with this chunk
                symbols = await self.symbol_repo.find_by_chunk_id(chunk.id)
                symbol_ids.extend([s.id for s in symbols])

            # Extract file ID
            if hasattr(chunk, 'file_id') and chunk.file_id:
                file_ids.add(str(chunk.file_id))

        # Get detailed symbol information
        symbols = []
        if symbol_ids:
            symbols = await self.symbol_repo.get_by_ids(list(set(symbol_ids)))

        return symbols, list(file_ids)

    async def _analyze_dependencies(
        self,
        project_id: str,
        file_ids: List[str]
    ) -> Dict[str, Any]:
        """Analyze dependencies for the given files."""
        try:
            # Get dependencies where these files are depended upon (outgoing dependencies)
            outgoing_deps = await self.dependency_repo.find_by_file_ids(file_ids)

            # Get dependencies where these files are the dependency (incoming dependencies)
            # We need a method to find dependencies by dependent_file_id
            incoming_deps = []
            for file_id in file_ids:
                deps = await self.dependency_repo.find_by_dependent_file_id(file_id)
                incoming_deps.extend(deps)

            # Combine and deduplicate
            all_deps = outgoing_deps + incoming_deps
            # Simple deduplication by (source_file_id, target_file_id) tuple
            seen = set()
            unique_deps = []
            for dep in all_deps:
                key = (dep.source_file_id, dep.target_file_id)
                if key not in seen:
                    seen.add(key)
                    unique_deps.append(dep)

            return {
                "dependencies": unique_deps,
                "outgoing_count": len(outgoing_deps),
                "incoming_count": len(incoming_deps)
            }
        except Exception as exc:
            logger.warning("dependency_analysis_failed", error=str(exc))
            return {
                "dependencies": [],
                "outgoing_count": 0,
                "incoming_count": 0
            }

    async def _identify_affected_files_for_change(
        self,
        project_id: str,
        change_query: str,
        context_symbols: List[Any],
        context_files: List[str],
        dependency_map: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Identify files that would be affected by implementing the change."""
        try:
            # Start with the files directly mentioned in the context
            directly_affected = set(context_files)

            # Add files that depend on the context files (if we change the context files, these might break)
            for dep in dependency_map.get("dependencies", []):
                if dep.target_file_id in context_files:  # target is what we depend on
                    directly_affected.add(dep.source_file_id)  # source depends on target
                elif dep.source_file_id in context_files:  # source is what we might change
                    directly_affected.add(dep.target_file_id)  # target depends on source

            # Get detailed information for the affected files
            affected_files = []
            for file_id in directly_affected:
                # Get symbols in this file from context
                file_symbols = [s for s in context_symbols if str(s.file_id) == file_id]

                # Determine why this file is affected
                reason = []
                if file_id in context_files:
                    reason.append("Directly referenced in change context")
                # Check dependencies
                for dep in dependency_map.get("dependencies", []):
                    if dep.source_file_id == file_id and dep.target_file_id in context_files:
                        reason.append(f"Depends on {dep.target_file_id}")
                    elif dep.target_file_id == file_id and dep.source_file_id in context_files:
                        reason.append(f"Is depended upon by {dep.source_file_id}")

                affected_files.append({
                    "file_id": file_id,
                    "reason": "; ".join(reason) if reason else "Related to change",
                    "symbols_count": len(file_symbols),
                    "change_type": "potential_modification"  # Could be refine later
                })

            # Also consider files that are highly connected in the dependency graph
            # For simplicity, we'll stick with the above for now

            return {
                "affected_files": affected_files,
                "directly_affected_count": len([f for f in affected_files if "Directly referenced" in f["reason"]]),
                "dependency_affected_count": len([f for f in affected_files if "Depends on" in f["reason"] or "Is depended upon" in f["reason"]]),
                "total_files_considered": len(context_files)
            }

        except Exception as exc:
            logger.warning("affected_files_identification_failed", error=str(exc))
            return {
                "affected_files": [],
                "directly_affected_count": 0,
                "dependency_affected_count": 0,
                "total_files_considered": 0
            }

    async def _generate_impact_summary(
        self,
        change_query: str,
        context: List[Tuple[Any, float]],
        affected_files_analysis: Dict[str, Any],
        dependency_map: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Generate a summary answer and assess risk using LLM."""
        try:
            # Format context for LLM
            context_text = self._format_context_for_llm(context)

            # Format dependency information
            dependency_text = self._format_dependency_info(dependency_map)

            # Format affected files
            affected_text = self._format_affected_files_for_llm(affected_files_analysis)

            # Create system prompt for change impact analysis
            system_prompt = """You are RepoMind AI's Change Impact Analysis Agent, specializing in analyzing how changes affect a codebase.
Your goal is to provide evidence-based analysis of which files are likely to be affected by a proposed change.
You must:
1. Base your analysis exclusively on the provided code evidence
2. Do not invent files or dependencies that are not in the evidence
3. Clearly separate what is evident from what is inferred
4. Provide specific file references when possible
5. Assess the risk level of the change
6. Be concise but thorough in your analysis"""

            # Create user prompt with all the analysis data
            
            system_prompt = """You are RepoMind AI, a code impact analyst.
Use only the supplied evidence. Never invent files or dependencies.
Separate confirmed facts from inferences. Be concise.
Assess risk as low, medium, or high."""

            user_prompt = f"""Analyze this proposed change:
{change_query}

Code evidence:
{context_text}

Dependencies:
{dependency_text}

Affected files:
{affected_text}

Return:
1. Impact summary.
2. Affected files and why.
3. Risk level with one-sentence justification.
4. Important assumptions, if any.

Use only relevant evidence. Keep the response under 250 words."""

            provider = get_llm_provider()
            options = GenerateOptions(
                temperature=0.1,
                max_tokens=384,
                system_prompt=system_prompt,
            )

            response = await provider.generate(user_prompt, options)


            # Determine confidence based on evidence quality
            confidence = self._assess_impact_confidence(
                context, affected_files_analysis, dependency_map
            )

            # Assess risk level based on the analysis
            risk_level = self._assess_risk_level(
                affected_files_analysis, dependency_map, change_query
            )

            return {
                "summary": response.content,
                "confidence": confidence,
                "risk_level": risk_level
            }

        except Exception as exc:
            logger.error("impact_summary_generation_failed", error=str(exc))
            return {
                "summary": "I encountered an error while generating the impact summary.",
                "confidence": "low",
                "risk_level": "unknown"
            }

    # Formatting helper methods

    def _format_context_for_llm(self, context: List[Tuple[Any, float]]) -> str:
        """Format context for LLM prompts."""
        if not context:
            return "No relevant code context found."

        formatted_chunks = []
        for i, (chunk, score) in enumerate(context[:3]):  # Top 5 chunks
            content = getattr(chunk, 'content', str(chunk))
            file_id = getattr(chunk, 'file_id', 'unknown')
            start_line = getattr(chunk, 'start_line', '?')
            end_line = getattr(chunk, 'end_line', '?')
            symbol = getattr(chunk, 'symbol', 'unknown')

            formatted_chunks.append(
                f"[File {file_id}:L{start_line}-L{end_line}] Symbol: {symbol} (Relevance: {score:.2f})\n{content}\n"
            )

        return "\n---\n".join(formatted_chunks)

    def _format_dependency_info(self, dependency_map: Dict[str, Any]) -> str:
        """Format dependency information using the actual Dependency model fields."""
        dependencies = dependency_map.get("dependencies", [])
        if not dependencies:
            return "No dependency relationships found."

        formatted = []
        for dep in dependencies[:5]:  # Top 10 dependencies
            # Support both SQLAlchemy model instances and dictionaries.
            if isinstance(dep, dict):
                source_file_id = dep.get("source_file_id")
                target_file_id = dep.get("target_file_id")
                target_module = dep.get("target_module")
                import_statement = dep.get("import_statement")
                symbol_name = dep.get("symbol_name")
                line_number = dep.get("line_number")
            else:
                source_file_id = getattr(dep, "source_file_id", None)
                target_file_id = getattr(dep, "target_file_id", None)
                target_module = getattr(dep, "target_module", None)
                import_statement = getattr(dep, "import_statement", None)
                symbol_name = getattr(dep, "symbol_name", None)
                line_number = getattr(dep, "line_number", None)

            source = source_file_id or "unknown source"
            target = target_file_id or target_module or "external/unknown target"
            relationship = symbol_name or target_module or import_statement or "dependency"
            line_info = f", line {line_number}" if line_number is not None else ""

            formatted.append(
                f"Source {source} -> Target {target} "
                f"(relationship: {relationship}{line_info})"
            )

        return "\n".join(formatted)

    def _format_affected_files_for_llm(self, affected_files_analysis: Dict[str, Any]) -> str:
        """Format affected files analysis for LLM prompts."""
        affected_files = affected_files_analysis.get("affected_files", [])
        if not affected_files:
            return "No specific affected files identified."

        formatted = []
        for file_info in affected_files[:5]:  # Top 10 affected files
            formatted.append(
                f"- File {file_info['file_id']}: {file_info['reason']}"
                f" ({file_info['symbols_count']} related symbols)"
            )

        return "\n".join(formatted)

    # Confidence and risk assessment methods

    def _assess_impact_confidence(
        self,
        context: List[Tuple[Any, float]],
        affected_files_analysis: Dict[str, Any],
        dependency_map: Dict[str, Any]
    ) -> str:
        """Assess confidence level for change impact analysis."""
        context_score = min(len(context) / 10.0, 1.0)  # Normalize to 0-1
        affected_score = min(len(affected_files_analysis.get("affected_files", [])) / 5.0, 1.0)
        dependency_score = min(len(dependency_map.get("dependencies", [])) / 10.0, 1.0)

        avg_score = (context_score + affected_score + dependency_score) / 3.0

        if avg_score >= 0.7:
            return "high"
        elif avg_score >= 0.4:
            return "medium"
        else:
            return "low"

    def _assess_risk_level(
        self,
        affected_files_analysis: Dict[str, Any],
        dependency_map: Dict[str, Any],
        change_query: str
    ) -> str:
        """Assess risk level based on the analysis."""
        # Simple heuristic: more affected files and more dependencies = higher risk
        affected_count = len(affected_files_analysis.get("affected_files", []))
        dependency_count = len(dependency_map.get("dependencies", []))

        # Normalize scores
        affected_score = min(affected_count / 10.0, 1.0)  # Assume >10 files is high risk
        dependency_score = min(dependency_count / 20.0, 1.0)  # Assume >20 deps is high risk

        # Also consider the nature of the change query
        change_lower = change_query.lower()
        risk_keywords = ["core", "base", "foundation", "breaking", "major"]
        risk_boost = 0.2 if any(keyword in change_lower for keyword in risk_keywords) else 0.0

        combined_score = (affected_score * 0.4 + dependency_score * 0.4) + risk_boost
        combined_score = min(combined_score, 1.0)  # Cap at 1.0

        if combined_score >= 0.7:
            return "high"
        elif combined_score >= 0.4:
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