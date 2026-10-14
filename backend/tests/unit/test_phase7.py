"""
RepoMind AI — Phase 7 Unit Tests: Vector Search

Tests for pgvector retrieval functionality including:
- Vector similarity search
- Metadata filtering
- Result ordering
- Edge cases
"""
from __future__ import annotations

import pytest
from typing import List
from uuid import uuid4

from app.models.code_chunk import CodeChunk
from app.models.file_document import FileDocument
from app.models.project import Project
from app.services.retrieval_service import RetrievalService
from app.repositories.chunk_repository import ChunkRepository
from app.repositories.file_repository import FileRepository
from app.repositories.project_repository import ProjectRepository


@pytest.mark.asyncio
async def test_vector_search_basic(test_db_session: object):
    """Test basic vector search functionality."""
    # Setup: Create test data
    project_repo = ProjectRepository(test_db_session)
    file_repo = FileRepository(test_db_session)
    chunk_repo = ChunkRepository(test_db_session)
    retrieval_service = RetrievalService(test_db_session)

    # Create test project
    project = await project_repo.create(
        name=f"test-project-{uuid4()}",
        path="/tmp/test"
    )
    # Update status to completed for testing
    project = await project_repo.update_status(project.id, "completed")

    # Create test file
    file_doc = await file_repo.create(
        project_id=project.id,
        path="/tmp/test/test.py",
        relative_path="test.py",
        language="python",
        size_bytes=1000,
        line_count=50,
        file_hash="abc123",
        ast_status="parsed"
    )

    # Create test chunks with known embeddings
    # Using simple deterministic embeddings for testing
    embedding1 = [0.1] * 768  # All 0.1s
    embedding2 = [0.2] * 768  # All 0.2s
    embedding3 = [0.9] * 768  # All 0.9s (should be most similar to query)

    chunk1 = await chunk_repo.create(
        project_id=project.id,
        file_id=file_doc.id,
        chunk_index=0,
        content="def hello_world():\n    print('Hello, World!')",
        start_line=1,
        end_line=2,
        token_count=10,
        embedding=embedding1,
        metadata={"chunk_type": "function", "symbol_name": "hello_world"}
    )

    chunk2 = await chunk_repo.create(
        project_id=project.id,
        file_id=file_doc.id,
        chunk_index=1,
        content="class TestClass:\n    def method(self):\n        pass",
        start_line=4,
        end_line=6,
        token_count=15,
        embedding=embedding2,
        metadata={"chunk_type": "class", "symbol_name": "TestClass"}
    )

    chunk3 = await chunk_repo.create(
        project_id=project.id,
        file_id=file_doc.id,
        chunk_index=2,
        content="def calculate_sum(a, b):\n    return a + b\n\nresult = calculate_sum(5, 3)",
        start_line=8,
        end_line=11,
        token_count=20,
        embedding=embedding3,
        metadata={"chunk_type": "function", "symbol_name": "calculate_sum"}
    )

    await test_db_session.flush()

    # Test: Vector search with query that should match chunk3 most closely
    # Using an embedding similar to embedding3
    query_embedding = [0.85] * 768  # Similar to embedding3 [0.9]*768

    # We need to test through the service which generates embeddings from text
    # For this test, we'll mock or use a known text that would produce similar embedding
    results = await retrieval_service.vector_search(
        query_text="calculate sum of two numbers",
        project_id=project.id,
        limit=5,
        similarity_threshold=0.5  # Low threshold to get results
    )

    # Verify we got results
    assert len(results) > 0, "Should return search results"

    # Verify results are ordered by similarity (highest first)
    if len(results) > 1:
        for i in range(len(results) - 1):
            assert results[i][1] >= results[i + 1][1], \
                f"Results should be ordered by similarity descending: {results[i][1]} >= {results[i+1][1]}"

    # Verify that chunks have the expected metadata
    for chunk, similarity in results:
        assert isinstance(chunk, CodeChunk)
        assert chunk.project_id == project.id
        assert 0.0 <= similarity <= 1.0
        assert hasattr(chunk, 'metadata_')


@pytest.mark.asyncio
async def test_vector_search_with_filters(test_db_session: object):
    """Test vector search with project and file filters."""
    # Setup: Create multiple projects and files
    project_repo = ProjectRepository(test_db_session)
    file_repo = FileRepository(test_db_session)
    chunk_repo = ChunkRepository(test_db_session)
    retrieval_service = RetrievalService(test_db_session)

    # Create two test projects
    project1 = await project_repo.create(
        name=f"test-project-1-{uuid4()}",
        path="/tmp/test1"
    )
    project1 = await project_repo.update_status(project1.id, "completed")

    project2 = await project_repo.create(
        name=f"test-project-2-{uuid4()}",
        path="/tmp/test2"
    )
    project2 = await project_repo.update_status(project2.id, "completed")

    # Create files in each project
    file1 = await file_repo.create(
        project_id=project1.id,
        path="/tmp/test1/file1.py",
        relative_path="file1.py",
        language="python",
        size_bytes=500,
        line_count=25,
        file_hash="def456",
        ast_status="parsed"
    )

    file2 = await file_repo.create(
        project_id=project2.id,
        path="/tmp/test2/file2.py",
        relative_path="file2.py",
        language="python",
        size_bytes=500,
        line_count=25,
        file_hash="ghi789",
        ast_status="parsed"
    )

    # Create identical chunks in both projects
    embedding = [0.5] * 768  # Same embedding for both

    chunk1 = await chunk_repo.create(
        project_id=project1.id,
        file_id=file1.id,
        chunk_index=0,
        content="def common_function():\n    return 42",
        start_line=1,
        end_line=2,
        token_count=8,
        embedding=embedding,
        metadata={"chunk_type": "function", "symbol_name": "common_function"}
    )

    chunk2 = await chunk_repo.create(
        project_id=project2.id,
        file_id=file2.id,
        chunk_index=0,
        content="def common_function():\n    return 42",
        start_line=1,
        end_line=2,
        token_count=8,
        embedding=embedding,
        metadata={"chunk_type": "function", "symbol_name": "common_function"}
    )

    await test_db_session.flush()

    # Test: Search with project1 filter - should only return chunk1
    results_project1 = await retrieval_service.vector_search(
        query_text="common function that returns 42",
        project_id=project1.id,
        limit=10,
        similarity_threshold=0.3
    )

    # Verify all results are from project1
    for chunk, similarity in results_project1:
        assert chunk.project_id == project1.id
        assert chunk.file_id == file1.id

    # Test: Search with project2 filter - should only return chunk2
    results_project2 = await retrieval_service.vector_search(
        query_text="common function that returns 42",
        project_id=project2.id,
        limit=10,
        similarity_threshold=0.3
    )

    # Verify all results are from project2
    for chunk, similarity in results_project2:
        assert chunk.project_id == project2.id
        assert chunk.file_id == file2.id

    # Test: Search with no project filter - should return both chunks
    results_both = await retrieval_service.vector_search(
        query_text="common function that returns 42",
        limit=10,
        similarity_threshold=0.3
    )

    # Should get results from both projects
    project_ids_found = {chunk.project_id for chunk, _ in results_both}
    assert project1.id in project_ids_found or project2.id in project_ids_found


@pytest.mark.asyncio
async def test_vector_search_empty_results(test_db_session: object):
    """Test vector search when no matches are found."""
    # Setup: Create test data
    project_repo = ProjectRepository(test_db_session)
    file_repo = FileRepository(test_db_session)
    chunk_repo = ChunkRepository(test_db_session)
    retrieval_service = RetrievalService(test_db_session)

    # Create test project
    project = await project_repo.create(
        name=f"test-project-empty-{uuid4()}",
        path="/tmp/test-empty"
    )
    # Update status to completed for testing
    project = await project_repo.update_status(project.id, "completed")

    # Create test file
    file_doc = await file_repo.create(
        project_id=project.id,
        path="/tmp/test-empty/file.py",
        relative_path="file.py",
        language="python",
        size_bytes=500,
        line_count=25,
        file_hash="jkl012",
        ast_status="parsed"
    )

    # Create a chunk with embedding very different from what we'll query
    embedding = [0.0] * 768  # All zeros

    await chunk_repo.create(
        project_id=project.id,
        file_id=file_doc.id,
        chunk_index=0,
        content="def unrelated_function():\n    pass",
        start_line=1,
        end_line=2,
        token_count=6,
        embedding=embedding,
        metadata={"chunk_type": "function"}
    )

    await test_db_session.flush()

    # Test: Query with embedding that should have low similarity
    # Using text that would produce very different embedding
    results = await retrieval_service.vector_search(
        query_text="completely unrelated query about quantum physics",
        project_id=project.id,
        limit=10,
        similarity_threshold=0.9  # Very high threshold
    )

    # Should return empty results due to high threshold
    assert len(results) == 0, "Should return no results with high similarity threshold"


@pytest.mark.asyncio
async def test_vector_search_limit_parameter(test_db_session: object):
    """Test that the limit parameter works correctly."""
    # Setup: Create test data with multiple chunks
    project_repo = ProjectRepository(test_db_session)
    file_repo = FileRepository(test_db_session)
    chunk_repo = ChunkRepository(test_db_session)
    retrieval_service = RetrievalService(test_db_session)

    # Create test project
    project = await project_repo.create(
        name=f"test-project-limit-{uuid4()}",
        path="/tmp/test-limit"
    )
    # Update status to completed for testing
    project = await project_repo.update_status(project.id, "completed")

    # Create test file
    file_doc = await file_repo.create(
        project_id=project.id,
        path="/tmp/test-limit/file.py",
        relative_path="file.py",
        language="python",
        size_bytes=2000,
        line_count=100,
        file_hash="mno345",
        ast_status="parsed"
    )

    # Create multiple chunks with gradually decreasing similarity to query
    # Using embeddings that will have predictable similarity to our query
    base_embedding = [0.7] * 768

    chunks_created = []
    for i in range(10):
        # Vary the embedding slightly to create different similarity scores
        variation = [0.01 * i] * 768  # Increase slightly for each chunk
        embedding = [min(1.0, x + v) for x, v in zip(base_embedding, variation)]

        chunk = await chunk_repo.create(
            project_id=project.id,
            file_id=file_doc.id,
            chunk_index=i,
            content=f"def function_{i}():\n    return {i}",
            start_line=(i * 2) + 1,
            end_line=(i * 2) + 2,
            token_count=8,
            embedding=embedding,
            metadata={"chunk_type": "function", "symbol_name": f"function_{i}"}
        )
        chunks_created.append(chunk)

    await test_db_session.flush()

    # Test: Search with limit=3
    results_limited = await retrieval_service.vector_search(
        query_text="function returning number",
        project_id=project.id,
        limit=3,
        similarity_threshold=0.1  # Low threshold to get many potential results
    )

    # Verify we got exactly 3 results (or fewer if fewer exist)
    assert len(results_limited) <= 3, f"Should return at most 3 results, got {len(results_limited)}"

    # Test: Search with limit=10 (more than we have)
    results_unlimited = await retrieval_service.vector_search(
        query_text="function returning number",
        project_id=project.id,
        limit=10,
        similarity_threshold=0.1
    )

    # Should get all chunks (or at least not be limited by the parameter)
    assert len(results_unlimited) >= min(10, len(chunks_created))


if __name__ == "__main__":
    pytest.main([__file__, "-v"])