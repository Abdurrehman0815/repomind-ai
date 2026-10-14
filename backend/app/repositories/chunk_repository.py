"""
RepoMind AI — CodeChunk Repository
"""
from typing import Sequence, Any, List, Tuple, Optional
import structlog
from sqlalchemy import select, delete, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.code_chunk import CodeChunk

logger = structlog.get_logger(__name__)


class ChunkRepository:
    """Data access layer for CodeChunk entities with vector support."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, chunk_id: str) -> CodeChunk | None:
        result = await self.session.execute(
            select(CodeChunk).where(CodeChunk.id == chunk_id)
        )
        return result.scalar_one_or_none()

    async def list_by_file(self, file_id: str) -> Sequence[CodeChunk]:
        result = await self.session.execute(
            select(CodeChunk)
            .where(CodeChunk.file_id == file_id)
            .order_by(CodeChunk.chunk_index)
        )
        return result.scalars().all()

    async def list_by_project(self, project_id: str) -> Sequence[CodeChunk]:
        result = await self.session.execute(
            select(CodeChunk)
            .where(CodeChunk.project_id == project_id)
            .order_by(CodeChunk.created_at)
        )
        return result.scalars().all()

    async def vector_search(
        self,
        query_embedding: List[float],
        project_id: Optional[str] = None,
        file_id: Optional[str] = None,
        limit: int = 10,
        similarity_threshold: float = 0.7,
    ) -> List[Tuple[CodeChunk, float]]:
        """
        Perform vector similarity search on code chunks.

        Args:
            query_embedding: Embedding vector for the query text
            project_id: Filter by project ID
            file_id: Filter by file ID
            limit: Maximum number of results to return
            similarity_threshold: Minimum similarity score (0-1)

        Returns:
            List of tuples (CodeChunk, similarity_score) ordered by similarity descending
        """
        # Build the SQL query for vector similarity search
        # Using cosine distance: 1 - cosine_similarity
        # We want results where cosine_similarity >= similarity_threshold
        # So: cosine_distance <= (1 - similarity_threshold)
        distance_threshold = 1.0 - similarity_threshold

        # Base query
        query = select(
            CodeChunk,
            (1 - CodeChunk.embedding.cosine_distance(query_embedding)).label('similarity')
        ).where(
            CodeChunk.embedding.is_not(None),  # Only chunks with embeddings
            (1 - CodeChunk.embedding.cosine_distance(query_embedding)) >= similarity_threshold
        )

        # Apply filters
        if project_id:
            query = query.where(CodeChunk.project_id == project_id)
        if file_id:
            query = query.where(CodeChunk.file_id == file_id)

        # Order by similarity descending and limit
        query = query.order_by(
            text('similarity DESC')
        ).limit(limit)

        try:
            result = await self.session.execute(query)
            rows = result.all()

            # Convert to list of (chunk, similarity) tuples
            results = []
            for row in rows:
                chunk = row.CodeChunk
                similarity = float(row.similarity)
                results.append((chunk, similarity))

            return results

        except Exception as e:
            logger.error(f"vector_search_failed: {str(e)}")
            return []

    async def create(
        self,
        project_id: str,
        file_id: str,
        chunk_index: int,
        content: str,
        start_line: int,
        end_line: int,
        token_count: int = 0,
        embedding: list[float] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> CodeChunk:
        chunk = CodeChunk(
            project_id=project_id,
            file_id=file_id,
            chunk_index=chunk_index,
            content=content,
            start_line=start_line,
            end_line=end_line,
            token_count=token_count,
            embedding=embedding,
            metadata_=metadata or {},
        )
        self.session.add(chunk)
        await self.session.flush()
        return chunk

    async def delete_by_file(self, file_id: str) -> int:
        result = await self.session.execute(
            delete(CodeChunk).where(CodeChunk.file_id == file_id)
        )
        await self.session.flush()
        return result.rowcount
