"""
RepoMind AI — Retrieval & Search API

Provides endpoints for vector search, hybrid search, and retrieval operations.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.db.session import get_db
from app.services.retrieval_service import RetrievalService
from app.models.code_chunk import CodeChunk

logger = structlog.get_logger(__name__)
router = APIRouter()


@router.get("/search/vector", status_code=status.HTTP_200_OK)
async def vector_search(
    q: str = Query(..., description="Query text to search for"),
    project_id: str | None = Query(None, description="Filter by project ID"),
    repository_id: str | None = Query(None, description="Filter by repository ID (maps to project_id)"),
    file_id: str | None = Query(None, description="Filter by file ID"),
    language: str | None = Query(None, description="Filter by language (future enhancement)"),
    limit: int = Query(10, ge=1, le=100, description="Maximum number of results to return"),
    threshold: float = Query(0.7, ge=0.0, le=1.0, description="Minimum similarity threshold (0-1)"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Perform vector similarity search on code chunks.

    Returns chunks ranked by semantic similarity to the query text.
    """
    service = RetrievalService(db)
    try:
        results = await service.vector_search(
            query_text=q,
            project_id=project_id,
            repository_id=repository_id,
            file_id=file_id,
            language=language,
            limit=limit,
            similarity_threshold=threshold,
        )

        # Format results for API response
        formatted_results = []
        for chunk, similarity in results:
            formatted_results.append({
                "id": chunk.id,
                "content": chunk.content,
                "start_line": chunk.start_line,
                "end_line": chunk.end_line,
                "token_count": chunk.token_count,
                "metadata": chunk.metadata_,
                "similarity": similarity,
                "file_id": chunk.file_id,
                "project_id": chunk.project_id,
                "chunk_index": chunk.chunk_index
            })

        logger.info(
            "vector_search_api_completed",
            query=q[:50],
            project_id=project_id,
            file_id=file_id,
            limit=limit,
            threshold=threshold,
            results_count=len(formatted_results)
        )

        return {
            "query": q,
            "results": formatted_results,
            "total": len(formatted_results),
            "limit": limit,
            "threshold": threshold
        }

    except Exception as exc:
        logger.error("vector_search_api_failed", error=str(exc), query=q[:100])
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Vector search failed: {exc}",
        )


@router.get("/search/hybrid", status_code=status.HTTP_200_OK)
async def hybrid_search(
    q: str = Query(..., description="Query text to search for"),
    project_id: str | None = Query(None, description="Filter by project ID"),
    repository_id: str | None = Query(None, description="Filter by repository ID (maps to project_id)"),
    file_id: str | None = Query(None, description="Filter by file ID"),
    language: str | None = Query(None, description="Filter by language (future enhancement)"),
    limit: int = Query(10, ge=1, le=100, description="Maximum number of results to return"),
    vector_weight: float = Query(0.7, ge=0.0, le=1.0, description="Weight for vector similarity"),
    text_weight: float = Query(0.3, ge=0.0, le=1.0, description="Weight for text search"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Perform hybrid search combining vector similarity and text search using rank fusion.

    Combines semantic vector search with PostgreSQL full-text search for improved results.
    """
    service = RetrievalService(db)
    try:
        results = await service.hybrid_search(
            query_text=q,
            project_id=project_id,
            repository_id=repository_id,
            file_id=file_id,
            language=language,
            limit=limit,
            vector_weight=vector_weight,
            text_weight=text_weight,
        )

        # Format results for API response
        formatted_results = []
        for chunk, score in results:
            formatted_results.append({
                "id": chunk.id,
                "content": chunk.content,
                "start_line": chunk.start_line,
                "end_line": chunk.end_line,
                "token_count": chunk.token_count,
                "metadata": chunk.metadata_,
                "score": score,
                "file_id": chunk.file_id,
                "project_id": chunk.project_id,
                "chunk_index": chunk.chunk_index
            })

        logger.info(
            "hybrid_search_api_completed",
            query=q[:50],
            project_id=project_id,
            file_id=file_id,
            limit=limit,
            vector_weight=vector_weight,
            text_weight=text_weight,
            results_count=len(formatted_results)
        )

        return {
            "query": q,
            "results": formatted_results,
            "total": len(formatted_results),
            "limit": limit,
            "vector_weight": vector_weight,
            "text_weight": text_weight
        }

    except Exception as exc:
        logger.error("hybrid_search_api_failed", error=str(exc), query=q[:100])
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Hybrid search failed: {exc}",
        )


@router.get("/chunks/{chunk_id}", status_code=status.HTTP_200_OK)
async def get_chunk(
    chunk_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Get a single code chunk by its ID.
    """
    service = RetrievalService(db)
    chunk = await service.get_chunk_by_id(chunk_id)

    if not chunk:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Chunk with ID '{chunk_id}' not found.",
        )

    return {
        "id": chunk.id,
        "content": chunk.content,
        "start_line": chunk.start_line,
        "end_line": chunk.end_line,
        "token_count": chunk.token_count,
        "metadata": chunk.metadata_,
        "file_id": chunk.file_id,
        "project_id": chunk.project_id,
        "chunk_index": chunk.chunk_index,
        "created_at": chunk.created_at.isoformat() if chunk.created_at else None
    }


@router.get("/projects/{project_id}/chunks", status_code=status.HTTP_200_OK)
async def get_project_chunks(
    project_id: str,
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of results to return"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Get chunks for a project with pagination.
    """
    service = RetrievalService(db)
    chunks = await service.get_chunks_by_project(
        project_id=project_id,
        limit=limit,
        offset=offset
    )

    # Format results for API response
    formatted_results = []
    for chunk in chunks:
        formatted_results.append({
            "id": chunk.id,
            "content": chunk.content,
            "start_line": chunk.start_line,
            "end_line": chunk.end_line,
            "token_count": chunk.token_count,
            "metadata": chunk.metadata_,
            "file_id": chunk.file_id,
            "project_id": chunk.project_id,
            "chunk_index": chunk.chunk_index,
            "created_at": chunk.created_at.isoformat() if chunk.created_at else None
        })

    return {
        "project_id": project_id,
        "chunks": formatted_results,
        "total": len(formatted_results),
        "limit": limit,
        "offset": offset
    }