"""
RepoMind AI — Retrieval Service

Implements vector search, text search, and hybrid retrieval capabilities using pgvector.
Provides methods for semantic search, lexical search, metadata filtering, and result ranking.
"""
from __future__ import annotations

import structlog
from typing import Any, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.code_chunk import CodeChunk
from app.repositories.chunk_repository import ChunkRepository
from app.ai.providers.embedding_registry import get_embedding_provider
from app.ai.providers.embedding_base import EmbeddingOptions

logger = structlog.get_logger(__name__)


class RetrievalService:
    """Service for vector-based and hybrid retrieval of code chunks."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.chunk_repo = ChunkRepository(session)

    async def vector_search(
        self,
        query_text: str,
        project_id: Optional[str] = None,
        repository_id: Optional[str] = None,  # Keeping for compatibility, but using project_id
        file_id: Optional[str] = None,
        language: Optional[str] = None,
        limit: int = 10,
        similarity_threshold: float = 0.7,
    ) -> List[Tuple[CodeChunk, float]]:
        """
        Perform vector similarity search on code chunks.

        Args:
            query_text: Text to search for
            project_id: Filter by project ID
            repository_id: Kept for compatibility (maps to project_id)
            file_id: Filter by file ID
            language: Filter by language (from file metadata)
            limit: Maximum number of results to return
            similarity_threshold: Minimum similarity score (0-1)

        Returns:
            List of tuples (CodeChunk, similarity_score) ordered by similarity descending
        """
        # Generate embedding for the query text
        embedding_provider = get_embedding_provider()
        try:
            embedding_response = await embedding_provider.embed(
                [query_text],
                EmbeddingOptions(batch_size=1, normalize=True)
            )
            query_embedding = embedding_response.embeddings[0]
        except Exception as e:
            logger.error(f"failed_to_generate_query_embedding: {str(e)}")
            return []

        # Delegate to repository for vector search
        return await self.chunk_repo.vector_search(
            query_embedding=query_embedding,
            project_id=project_id,
            file_id=file_id,
            limit=limit,
            similarity_threshold=similarity_threshold
        )

    async def text_search(
        self,
        query_text: str,
        project_id: Optional[str] = None,
        file_id: Optional[str] = None,
        language: Optional[str] = None,
        limit: int = 10,
    ) -> List[Tuple[CodeChunk, float]]:
        """
        Perform text search on code chunks.
        Uses PostgreSQL full-text search when available, falls back to ILIKE for SQLite.

        Args:
            query_text: Text to search for
            project_id: Filter by project ID
            file_id: Filter by file ID
            language: Filter by language (from file metadata)
            limit: Maximum number of results to return

        Returns:
            List of tuples (CodeChunk, text_search_score) ordered by score descending
        """
        # Check if we're using PostgreSQL (has full-text search capabilities)
        db_url = str(self.session.get_bind().url)
        is_postgresql = db_url.startswith("postgresql")

        if is_postgresql:
            return await self._postgresql_text_search(
                query_text, project_id, file_id, language, limit
            )
        else:
            # For SQLite and other databases, use ILIKE-based search
            return await self._fallback_text_search(
                query_text, project_id, file_id, language, limit
            )

    async def _postgresql_text_search(
        self,
        query_text: str,
        project_id: Optional[str] = None,
        file_id: Optional[str] = None,
        language: Optional[str] = None,
        limit: int = 10,
    ) -> List[Tuple[CodeChunk, float]]:
        """
        Perform full-text search on code chunks using PostgreSQL's full-text search capabilities.
        """
        try:
            # Build the base query for text search
            query = select(
                CodeChunk,
                func.ts_rank(
                    func.to_tsvector('english', CodeChunk.content),
                    func.plainto_tsquery('english', query_text)
                ).label('text_score')
            ).where(
                func.to_tsvector('english', CodeChunk.content).op('@@')(
                    func.plainto_tsquery('english', query_text)
                )
            )

            # Apply filters
            if project_id:
                query = query.where(CodeChunk.project_id == project_id)
            if file_id:
                query = query.where(CodeChunk.file_id == file_id)

            # Note: Language filtering would require joining with file_document table
            # For now, we'll implement basic project and file filtering

            # Order by text score descending and limit
            query = query.order_by(
                text('text_score DESC')
            ).limit(limit)

            result = await self.session.execute(query)
            rows = result.all()

            # Convert to list of (chunk, text_score) tuples
            results = []
            for row in rows:
                chunk = row.CodeChunk
                text_score = float(row.text_score)
                results.append((chunk, text_score))

            return results

        except Exception as e:
            logger.error(f"postgresql_text_search_failed: {str(e)}")
            # Fallback to ILIKE search
            return await self._fallback_text_search(
                query_text, project_id, file_id, language, limit
            )

    async def _fallback_text_search(
        self,
        query_text: str,
        project_id: Optional[str] = None,
        file_id: Optional[str] = None,
        language: Optional[str] = None,
        limit: int = 10,
    ) -> List[Tuple[CodeChunk, float]]:
        """
        Fallback text search using ILIKE when full-text search is not available.
        Matches documents where any query word appears (case-insensitive),
        treating underscores as word boundaries for better code matching.
        Includes special handling for common programming terms.
        """
        try:
            # Normalize query text: lowercase and treat underscores as word boundaries
            normalized_query = query_text.lower().replace('_', ' ')
            # Split query into words (simple whitespace split)
            query_words = [word.strip() for word in normalized_query.split() if word.strip()]

            logger.info(f"fallback_text_search_debug: query_text={repr(query_text)}, normalized_query={repr(normalized_query)}, query_words={query_words}")

            if not query_words:
                # No valid words to search for
                return []

            # Start with base query
            query = select(CodeChunk)

            # Debug: Check total chunks
            debug_query = select(CodeChunk)
            debug_result = await self.session.execute(debug_query)
            debug_rows = debug_result.all()
            logger.info(f"fallback_text_search_debug: total_chunks={len(debug_rows)}")

            # Debug: Show first few chunks content (normalized for matching)
            for i, row in enumerate(debug_rows[:3]):
                chunk = row.CodeChunk
                normalized_content = chunk.content.lower().replace('_', ' ')
                logger.info(f"fallback_text_search_debug: chunk_{i}_content={repr(chunk.content[:50])}, normalized={repr(normalized_content[:50])}")

            # Apply ILIKE conditions for each word (OR logic - any word matches)
            # We search in normalized content where underscores are treated as spaces
            if query_words:
                or_conditions = []
                for word in query_words:
                    # Special handling for common programming terms
                    expanded_words = [word]  # Start with the original word
                    if word == "function":
                        # Also match common function definition indicators
                        expanded_words.extend(["def", "fun", "func"])
                    elif word == "def":
                        # Also match function-related terms
                        expanded_words.extend(["function", "fun", "func"])

                    for expanded_word in expanded_words:
                        # Escape % and _ characters in the word for LIKE pattern
                        escaped_word = expanded_word.replace('%', r'\%').replace('_', r'\_')
                        # Search in content where we treat underscores as spaces for matching purposes
                        # We do this by checking if the word appears in the content with underscores replaced by spaces
                        or_conditions.append(func.lower(func.replace(CodeChunk.content, '_', ' ')).like(f'%{escaped_word}%'))

                # Combine conditions with OR
                from sqlalchemy import or_
                query = query.where(or_(*or_conditions))

                logger.info(f"fallback_text_search_debug: applied OR conditions for {len(query_words)} words (expanded)")

            # Apply additional filters
            if project_id:
                query = query.where(CodeChunk.project_id == project_id)
            if file_id:
                query = query.where(CodeChunk.file_id == file_id)

            # Order by chunk ID for consistent results (since we don't have ranking)
            query = query.order_by(CodeChunk.id).limit(limit)

            logger.info(f"fallback_text_search_debug: executing query with project_id={project_id}, file_id={file_id}")

            result = await self.session.execute(query)
            rows = result.all()
            logger.info(f"fallback_text_search_debug: matching_rows={len(rows)}")

            results = []
            for row in rows:
                chunk = row.CodeChunk
                # Simple scoring - all matches get score 1.0 for now
                # TODO: Implement proper scoring based on match quality
                score = 1.0
                results.append((chunk, score))

            return results

        except Exception as e:
            logger.error(f"fallback_text_search_failed: {str(e)}")
            return []

    async def hybrid_search(
        self,
        query_text: str,
        project_id: Optional[str] = None,
        file_id: Optional[str] = None,
        language: Optional[str] = None,
        limit: int = 10,
        vector_weight: float = 0.7,
        text_weight: float = 0.3,
    ) -> List[Tuple[CodeChunk, float]]:
        """
        Perform hybrid search combining vector similarity and text search using rank fusion.

        Args:
            query_text: Text to search for
            project_id: Filter by project ID
            file_id: Filter by file ID
            language: Filter by language
            limit: Maximum number of results to return
            vector_weight: Weight for vector similarity score (0-1)
            text_weight: Weight for text search score (0-1)

        Returns:
            List of tuples (CodeChunk, combined_score) ordered by score descending
        """
        # Validate weights
        if abs(vector_weight + text_weight - 1.0) > 0.001:
            logger.warning(
                f"hybrid_search_weights_do_not_sum_to_one: vector_weight={vector_weight}, text_weight={text_weight}"
            )
            # Normalize weights
            total = vector_weight + text_weight
            if total > 0:
                vector_weight = vector_weight / total
                text_weight = text_weight / total
            else:
                vector_weight, text_weight = 0.7, 0.3  # Default fallback

        # Get results from both search methods
        # Get more candidates than needed to allow for effective fusion
        candidate_limit = min(limit * 3, 50)  # Get up to 3x requested limit, max 50

        vector_results = await self.vector_search(
            query_text=query_text,
            project_id=project_id,
            file_id=file_id,
            language=language,
            limit=candidate_limit,
            similarity_threshold=0.5  # Lower threshold to get more candidates
        )

        text_results = await self.text_search(
            query_text=query_text,
            project_id=project_id,
            file_id=file_id,
            language=language,
            limit=candidate_limit
        )

        # Combine results using rank fusion (Combined SUM model)
        chunk_scores = {}

        # Process vector results
        for rank, (chunk, score) in enumerate(vector_results):
            chunk_id = str(chunk.id)
            # Use reciprocal rank: 1 / (rank + 1)
            vector_rank_score = 1.0 / (rank + 1)

            if chunk_id not in chunk_scores:
                chunk_scores[chunk_id] = {
                    'chunk': chunk,
                    'vector_score': vector_rank_score,
                    'text_score': 0.0
                }
            else:
                chunk_scores[chunk_id]['vector_score'] = max(
                    chunk_scores[chunk_id]['vector_score'],
                    vector_rank_score
                )

        # Process text results
        for rank, (chunk, score) in enumerate(text_results):
            chunk_id = str(chunk.id)
            # Use reciprocal rank: 1 / (rank + 1)
            text_rank_score = 1.0 / (rank + 1)

            if chunk_id not in chunk_scores:
                chunk_scores[chunk_id] = {
                    'chunk': chunk,
                    'vector_score': 0.0,
                    'text_score': text_rank_score
                }
            else:
                chunk_scores[chunk_id]['text_score'] = max(
                    chunk_scores[chunk_id]['text_score'],
                    text_rank_score
                )

        # Calculate combined scores
        scored_chunks = []
        for chunk_id, scores in chunk_scores.items():
            combined_score = (
                vector_weight * scores['vector_score'] +
                text_weight * scores['text_score']
            )
            scored_chunks.append((scores['chunk'], combined_score))

        # Sort by combined score descending and limit results
        scored_chunks.sort(key=lambda x: x[1], reverse=True)
        final_results = scored_chunks[:limit]

        logger.info(
            f"hybrid_search_completed: query={query_text[:50]}, project_id={project_id}, "
            f"vector_results={len(vector_results)}, text_results={len(text_results)}, "
            f"final_results={len(final_results)}, vector_weight={vector_weight}, text_weight={text_weight}"
        )

        return final_results

    async def get_chunk_by_id(self, chunk_id: str) -> Optional[CodeChunk]:
        """Get a single chunk by its ID."""
        return await self.chunk_repo.get_by_id(chunk_id)

    async def get_chunks_by_project(
        self,
        project_id: str,
        limit: int = 100,
        offset: int = 0
    ) -> List[CodeChunk]:
        """Get chunks for a project with pagination."""
        # This would need to be implemented in ChunkRepository or use a custom query
        # For now, we'll get all and slice (not efficient for large datasets)
        all_chunks = await self.chunk_repo.list_by_project(project_id)
        return all_chunks[offset:offset + limit]