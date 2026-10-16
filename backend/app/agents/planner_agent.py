"""
RepoMind AI — Implementation Planner Agent

Implements a specialized agent for creating implementation plans for feature requirements.
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


class PlannerAgent:
    """
    Specialized agent for creating implementation plans for feature requirements.

    Handles sophisticated planning tasks that require:
    - Understanding feature requirements
    - Analyzing existing codebase structure
    - Identifying affected files and components
    - Generating step-by-step implementation sequences
    - Identifying required tests and potential risks
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

    async def create_implementation_plan(
        self,
        project_id: str,
        feature_requirement: str,
        session_id: str
    ) -> Dict[str, Any]:
        """
        Create an implementation plan for a given feature requirement.

        Args:
            project_id: ID of the project to plan for
            feature_requirement: Description of the feature to implement
            session_id: ID of the chat session

        Returns:
            Dictionary containing the implementation plan and metadata
        """
        logger.info(
            "starting_implementation_planning",
            project_id=project_id,
            feature_requirement=feature_requirement[:50],
            session_id=session_id
        )

        try:
            # Step 1: Retrieve context related to the feature requirement
            retrieved_context = await self._retrieve_feature_context(
                project_id=project_id,
                feature_requirement=feature_requirement
            )

            if not retrieved_context:
                return {
                    "answer": "I could not find sufficient evidence in the codebase to create an implementation plan for this feature.",
                    "confidence": "low",
                    "sources": [],
                    "plan_type": "implementation_plan"
                }

            # Step 2: Analyze the existing codebase structure related to the feature
            structure_analysis = await self._analyze_feature_structure(
                project_id=project_id,
                feature_requirement=feature_requirement,
                context_chunks=[chunk for chunk, _ in retrieved_context]
            )

            # Step 3: Identify affected files and components
            affected_files_analysis = await self._identify_affected_files(
                project_id=project_id,
                feature_requirement=feature_requirement,
                context_chunks=[chunk for chunk, _ in retrieved_context],
                structure_analysis=structure_analysis
            )

            # Step 4: Generate implementation plan
            implementation_plan = await self._generate_implementation_plan(
                feature_requirement=feature_requirement,
                context=retrieved_context,
                structure_analysis=structure_analysis,
                affected_files_analysis=affected_files_analysis
            )

            # Step 5: Validate and format citations
            citations = await self._validate_and_format_citations(
                retrieved_context=retrieved_context,
                project_id=project_id
            )

            logger.info(
                "implementation_planning_completed",
                project_id=project_id,
                confidence=implementation_plan.get("confidence", "medium"),
                sources_count=len(citations)
            )

            return {
                "answer": implementation_plan.get("plan", ""),
                "confidence": implementation_plan.get("confidence", "medium"),
                "sources": citations,
                "plan_type": "implementation_plan",
                "metadata": {
                    "context_chunks_used": len(retrieved_context),
                    "affected_files_count": len(affected_files_analysis.get("affected_files", [])),
                    "new_components_count": len(implementation_plan.get("new_components", [])),
                    "tests_required_count": len(implementation_plan.get("tests_required", []))
                }
            }

        except Exception as exc:
            logger.error(
                "implementation_planning_failed",
                error=str(exc),
                project_id=project_id,
                exc_info=True
            )

            return {
                "answer": "I encountered an error while creating the implementation plan. Please try again.",
                "confidence": "low",
                "sources": [],
                "plan_type": "implementation_plan",
                "error": str(exc)
            }

    # Helper methods for planning

    async def _retrieve_feature_context(
        self,
        project_id: str,
        feature_requirement: str
    ) -> List[Tuple[Any, float]]:
        """Retrieve context related to the feature requirement."""
        try:
            # Use hybrid search to get relevant chunks for the feature
            results = await self.retrieval_service.hybrid_search(
                query_text=feature_requirement,
                project_id=project_id,
                limit=15,  # Get more results for feature planning
                vector_weight=0.6,
                text_weight=0.4
            )
            return results
        except Exception as exc:
            logger.warning("feature_context_retrieval_failed", error=str(exc))
            return []

    async def _analyze_feature_structure(
        self,
        project_id: str,
        feature_requirement: str,
        context_chunks: List[Any]
    ) -> Dict[str, Any]:
        """Analyze the existing codebase structure related to the feature."""
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

            # Analyze structure
            key_symbols = []
            existing_components = []
            file_distribution = {}

            for symbol in symbols:
                # Categorize symbol importance
                if symbol.kind in ['class', 'function', 'method', 'interface', 'module']:
                    key_symbols.append({
                        "id": str(symbol.id),
                        "name": symbol.name,
                        "kind": symbol.kind,
                        "file_id": str(symbol.file_id) if symbol.file_id else None,
                        "line_start": symbol.start_line,
                        "line_end": symbol.end_line,
                        "docstring": getattr(symbol, 'docstring', None)
                    })

                # Track existing components by file
                file_id = str(symbol.file_id) if symbol.file_id else "unknown"
                if file_id not in file_distribution:
                    file_distribution[file_id] = []
                file_distribution[file_id].append({
                    "name": symbol.name,
                    "kind": symbol.kind,
                    "line_start": symbol.start_line
                })

            return {
                "key_symbols": key_symbols,
                "existing_components": existing_components,
                "file_distribution": file_distribution,
                "total_symbols_analyzed": len(symbols)
            }

        except Exception as exc:
            logger.warning("feature_structure_analysis_failed", error=str(exc))
            return {
                "key_symbols": [],
                "existing_components": [],
                "file_distribution": {},
                "total_symbols_analyzed": 0
            }

    async def _identify_affected_files(
        self,
        project_id: str,
        feature_requirement: str,
        context_chunks: List[Any],
        structure_analysis: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Identify files that would be affected by implementing the feature."""
        try:
            # Get file IDs from symbols in context
            file_ids = set()
            for chunk in context_chunks:
                if hasattr(chunk, 'file_id') and chunk.file_id:
                    file_ids.add(str(chunk.file_id))

            # Get dependencies for these files to understand impact
            dependencies = []
            if file_ids:
                dependencies = await self.dependency_repo.find_by_file_ids(list(file_ids))

            # Analyze which files would need modification
            affected_files = []
            new_files_needed = []

            # Check existing files that might need modification
            for file_id in file_ids:
                # Get symbols in this file to understand what's already there
                file_symbols = [s for s in structure_analysis.get("key_symbols", [])
                              if s.get("file_id") == file_id]

                affected_files.append({
                    "file_id": file_id,
                    "reason": "Contains related functionality that may need modification",
                    "existing_symbols_count": len(file_symbols),
                    "modification_type": "modify"  # Could be modify, extend, or refactor
                })

            # Identify potential new files needed based on feature requirements
            # This is a simplified approach - in practice would be more sophisticated
            feature_lower = feature_requirement.lower()
            if any(keyword in feature_lower for keyword in ["auth", "login", "authentication"]):
                new_files_needed.append({
                    "suggested_path": "src/auth/",
                    "purpose": "Authentication-related components",
                    "suggested_files": ["auth/service.py", "auth/router.py", "auth/models.py"]
                })
            elif any(keyword in feature_lower for keyword in ["api", "endpoint", "route"]):
                new_files_needed.append({
                    "suggested_path": "src/api/",
                    "purpose": "API endpoint components",
                    "suggested_files": ["api/routes.py", "api/handlers.py"]
                })
            elif any(keyword in feature_lower for keyword in ["model", "database", "data"]):
                new_files_needed.append({
                    "suggested_path": "src/models/",
                    "purpose": "Data model components",
                    "suggested_files": ["models/entity.py", "models/repository.py"]
                })

            return {
                "affected_files": affected_files,
                "new_files_needed": new_files_needed,
                "dependencies_impact": len(dependencies),
                "total_files_considered": len(file_ids)
            }

        except Exception as exc:
            logger.warning("affected_files_identification_failed", error=str(exc))
            return {
                "affected_files": [],
                "new_files_needed": [],
                "dependencies_impact": 0,
                "total_files_considered": 0
            }

    async def _generate_implementation_plan(
        self,
        feature_requirement: str,
        context: List[Tuple[Any, float]],
        structure_analysis: Dict[str, Any],
        affected_files_analysis: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Generate implementation plan using LLM with analyzed data."""
        try:
            # Format context for LLM
            context_text = self._format_detailed_context_for_llm(context)

            # Format structure analysis
            structure_text = self._format_structure_analysis(structure_analysis)

            # Format affected files analysis
            affected_text = self._format_affected_files_analysis(affected_files_analysis)

            # Create system prompt for implementation planning
            system_prompt = """You are RepoMind AI's Implementation Planner Agent, specializing in creating software implementation plans.
Your goal is to create detailed, evidence-based implementation plans for feature requirements.
You must:
1. Base your plan exclusively on the provided code evidence
2. Do not invent components or files that are not suggested by the evidence
3. Clearly separate what is evident from what is inferred
4. Provide specific file references and line numbers when possible
5. Create a logical sequence of implementation steps
6. Identify required tests and potential risks
7. Be concise but thorough in your planning"""

            # Create user prompt with all the analysis data
            user_prompt = f"""Based on the following codebase analysis, please create an implementation plan for the feature requirement.

FEATURE REQUIREMENT: {feature_requirement}

CODE CONTEXT:
{context_text}

EXISTING CODEBASE STRUCTURE:
{structure_text}

AFFECTED FILES ANALYSIS:
{affected_text}

Please provide a comprehensive implementation plan that includes:
1. Summary of the feature to be implemented
2. List of affected files (with specific paths and reasons)
3. Change sequence (ordered steps to implement the feature)
4. New components that need to be created
5. Tests required to validate the implementation
6. Potential risks and mitigation strategies
7. Any assumptions made during planning

Format your response as a clear, actionable implementation plan that a developer could follow."""

            # Get LLM provider and generate plan
            provider = get_llm_provider()
            options = GenerateOptions(
                temperature=0.2,
                max_tokens=3072,  # Increased for detailed planning
                system_prompt=system_prompt
            )

            response = await provider.generate(user_prompt, options)

            # Determine confidence based on evidence quality
            confidence = self._assess_plan_confidence(
                context, structure_analysis, affected_files_analysis
            )

            # Extract structured information from the response (simplified)
            # In a more sophisticated implementation, we would parse this into structured fields
            return {
                "plan": response.content,
                "confidence": confidence,
                "plan_complete": True,
                # These would ideally be parsed from the response, but for now we'll estimate
                "affected_files": affected_files_analysis.get("affected_files", []),
                "new_components": self._extract_new_components_from_plan(response.content),
                "tests_required": self._extract_tests_from_plan(response.content),
                "risks": self._extract_risks_from_plan(response.content),
                "assumptions": self._extract_assumptions_from_plan(response.content)
            }

        except Exception as exc:
            logger.error("implementation_plan_generation_failed", error=str(exc))
            return {
                "plan": "I encountered an error while generating the implementation plan.",
                "confidence": "low",
                "plan_complete": False
            }

    # Formatting helper methods

    def _format_detailed_context_for_llm(self, context: List[Tuple[Any, float]]) -> str:
        """Format detailed context for LLM prompts."""
        if not context:
            return "No relevant code context found."

        formatted_chunks = []
        for i, (chunk, score) in enumerate(context[:10]):  # Top 10 chunks
            content = getattr(chunk, 'content', str(chunk))
            file_id = getattr(chunk, 'file_id', 'unknown')
            start_line = getattr(chunk, 'start_line', '?')
            end_line = getattr(chunk, 'end_line', '?')
            symbol = getattr(chunk, 'symbol', 'unknown')

            formatted_chunks.append(
                f"[File {file_id}:L{start_line}-L{end_line}] Symbol: {symbol} (Relevance: {score:.2f})\n{content}\n"
            )

        return "\n---\n".join(formatted_chunks)

    def _format_structure_analysis(self, structure_analysis: Dict[str, Any]) -> str:
        """Format structure analysis for LLM prompts."""
        key_symbols = structure_analysis.get("key_symbols", [])
        if not key_symbols:
            return "No key symbols identified in the context."

        formatted = []
        for symbol in key_symbols[:10]:  # Top 10 symbols
            formatted.append(
                f"- {symbol['name']} ({symbol['kind']}) in File {symbol['file_id']}:L{symbol['line_start']}-L{symbol['line_end']}"
                f"{f': {symbol['docstring'][:100]}...' if symbol.get('docstring') else ''}"
            )

        return "\n".join(formatted)

    def _format_affected_files_analysis(self, affected_files_analysis: Dict[str, Any]) -> str:
        """Format affected files analysis for LLM prompts."""
        affected_files = affected_files_analysis.get("affected_files", [])
        new_files_needed = affected_files_analysis.get("new_files_needed", [])

        if not affected_files and not new_files_needed:
            return "No specific affected files identified."

        formatted = []

        if affected_files:
            formatted.append("FILES THAT MAY NEED MODIFICATION:")
            for file_info in affected_files[:5]:  # Top 5
                formatted.append(
                    f"- File {file_info['file_id']}: {file_info['reason']}"
                    f" ({file_info['existing_symbols_count']} related symbols)"
                )

        if new_files_needed:
            formatted.append("\nSUGGESTED NEW FILES TO CREATE:")
            for new_file_info in new_files_needed[:3]:  # Top 3
                formatted.append(
                    f"- Path: {new_file_info['suggested_path']}"
                    f" (Purpose: {new_file_info['purpose']})"
                )
                for suggested_file in new_file_info.get('suggested_files', [])[:2]:  # Top 2 suggested files
                    formatted.append(f"  * {suggested_file}")

        return "\n".join(formatted)

    # Confidence assessment methods

    def _assess_plan_confidence(
        self,
        context: List[Tuple[Any, float]],
        structure_analysis: Dict[str, Any],
        affected_files_analysis: Dict[str, Any]
    ) -> str:
        """Assess confidence level for implementation plan."""
        context_score = min(len(context) / 15.0, 1.0)  # Normalize to 0-1
        structure_score = min(len(structure_analysis.get("key_symbols", [])) / 10.0, 1.0)
        affected_score = min(len(affected_files_analysis.get("affected_files", [])) / 5.0, 1.0)

        avg_score = (context_score + structure_score + affected_score) / 3.0

        if avg_score >= 0.7:
            return "high"
        elif avg_score >= 0.4:
            return "medium"
        else:
            return "low"

    # Helper methods to extract structured data from plan response
    # These are simplified - in a production system we might use structured output from the LLM

    def _extract_new_components_from_plan(self, plan_text: str) -> List[Dict[str, Any]]:
        """Extract new components mentioned in the plan."""
        # Simplified extraction - look for common patterns
        components = []
        lines = plan_text.split('\n')
        for line in lines:
            line_lower = line.lower()
            if any(keyword in line_lower for keyword in ['create', 'new', 'add']) and \
               any(keyword in line_lower for keyword in ['class', 'function', 'component', 'module']):
                components.append({
                    "name": "extracted_from_plan",  # Would be parsed properly in reality
                    "type": "component",
                    "description": line.strip()[:100]
                })
        return components[:5]  # Limit to prevent overload

    def _extract_tests_from_plan(self, plan_text: str) -> List[Dict[str, Any]]:
        """Extract test requirements mentioned in the plan."""
        tests = []
        lines = plan_text.split('\n')
        for line in lines:
            line_lower = line.lower()
            if any(keyword in line_lower for keyword in ['test', 'testing', 'validate', 'verify']):
                tests.append({
                    "type": "test",
                    "description": line.strip()[:100]
                })
        return tests[:5]  # Limit to prevent overload

    def _extract_risks_from_plan(self, plan_text: str) -> List[Dict[str, Any]]:
        """Extract risks mentioned in the plan."""
        risks = []
        lines = plan_text.split('\n')
        for line in lines:
            line_lower = line.lower()
            if any(keyword in line_lower for keyword in ['risk', 'challenge', 'difficulty', 'limitation']):
                risks.append({
                    "type": "risk",
                    "description": line.strip()[:100]
                })
        return risks[:5]  # Limit to prevent overload

    def _extract_assumptions_from_plan(self, plan_text: str) -> List[Dict[str, Any]]:
        """Extract assumptions mentioned in the plan."""
        assumptions = []
        lines = plan_text.split('\n')
        for line in lines:
            line_lower = line.lower()
            if any(keyword in line_lower for keyword in ['assume', 'assuming', 'assumption', 'presume']):
                assumptions.append({
                    "type": "assumption",
                    "description": line.strip()[:100]
                })
        return assumptions[:5]  # Limit to prevent overload

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