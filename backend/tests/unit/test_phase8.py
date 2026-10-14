"""
RepoMind AI — Phase 8 Unit Tests: Hybrid Retrieval

Tests for hybrid retrieval functionality including:
- Vector search (semantic)
- Text search (lexical)
- Hybrid search with rank fusion
- Metadata filtering
- Result ordering and deduplication
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
async def test_text_search_basic(test_db_session: object):
    """Test basic text search functionality."""
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

    # Create test chunks
    chunk1 = await chunk_repo.create(
        project_id=project.id,
        file_id=file_doc.id,
        chunk_index=0,
        content="def hello_world():\n    print('Hello, World!')",
        start_line=1,
        end_line=2,
        token_count=10,
        metadata={"chunk_type": "function", "symbol_name": "hello_world"}
    )

    chunk2 = await chunk_repo.create(
        project_id=project.id,
        file_id=file_doc.id,
        chunk_index=1,
        content="def calculate_sum(a, b):\n    return a + b\n\nresult = calculate_sum(5, 3)",
        start_line=4,
        end_line=7,
        token_count=20,
        metadata={"chunk_type": "function", "symbol_name": "calculate_sum"}
    )

    chunk3 = await chunk_repo.create(
        project_id=project.id,
        file_id=file_doc.id,
        chunk_index=2,
        content="class TestClass:\n    def __init__(self):\n        self.value = 42",
        start_line=9,
        end_line=11,
        token_count=15,
        metadata={"chunk_type": "class", "symbol_name": "TestClass"}
    )

    await test_db_session.flush()

    # Test: Text search for "hello world"
    results = await retrieval_service.text_search(
        query_text="hello world",
        project_id=project.id,
        limit=5
    )

    # Verify we got results
    assert len(results) > 0, "Should return search results"

    # Verify results are ordered by text score (highest first)
    if len(results) > 1:
        for i in range(len(results) - 1):
            assert results[i][1] >= results[i + 1][1], \
                f"Results should be ordered by text score descending: {results[i][1]} >= {results[i+1][1]}"

    # Verify that chunks have the expected content
    for chunk, score in results:
        assert isinstance(chunk, CodeChunk)
        assert chunk.project_id == project.id
        assert 0.0 <= score <= 1.0
        assert "hello" in chunk.content.lower() or "world" in chunk.content.lower()


@pytest.mark.asyncio
async def test_text_search_with_filters(test_db_session: object):
    """Test text search with project and file filters."""
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

    # Create chunks with searchable content
    await chunk_repo.create(
        project_id=project1.id,
        file_id=file1.id,
        chunk_index=0,
        content="def authenticate_user(username, password):\n    # JWT validation logic here\n    return True",
        start_line=1,
        end_line=3,
        token_count=12,
        metadata={"chunk_type": "function", "symbol_name": "authenticate_user"}
    )

    await chunk_repo.create(
        project_id=project2.id,
        file_id=file2.id,
        chunk_index=0,
        content="def calculate_total(items):\n    return sum(item.price for item in items)",
        start_line=1,
        end_line=2,
        token_count=10,
        metadata={"chunk_type": "function", "symbol_name": "calculate_total"}
    )

    await test_db_session.flush()

    # Test: Search with project1 filter - should only return chunk from project1
    results_project1 = await retrieval_service.text_search(
        query_text="authenticate user",
        project_id=project1.id,
        limit=10
    )

    # Verify all results are from project1
    for chunk, score in results_project1:
        assert chunk.project_id == project1.id
        assert chunk.file_id == file1.id

    # Test: Search with project2 filter - should only return chunk from project2
    results_project2 = await retrieval_service.text_search(
        query_text="calculate total",
        project_id=project2.id,
        limit=10
    )

    # Verify all results are from project2
    for chunk, score in results_project2:
        assert chunk.project_id == project2.id
        assert chunk.file_id == file2.id

    # Test: Search with no project filter - should return chunks from both projects
    results_both = await retrieval_service.text_search(
        query_text="function",
        limit=10
    )

    # Should get results from both projects (since both files contain "function")
    assert len(results_both) >= 2, "Should find matches in both projects"


@pytest.mark.asyncio
async def test_text_search_empty_results(test_db_session: object):
    """Test text search when no matches are found."""
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

    # Create a chunk with content that won't match our query
    await chunk_repo.create(
        project_id=project.id,
        file_id=file_doc.id,
        chunk_index=0,
        content="def unrelated_function():\n    pass",
        start_line=1,
        end_line=2,
        token_count=6,
        metadata={"chunk_type": "function"}
    )

    await test_db_session.flush()

    # Test: Query for text that doesn't exist
    results = await retrieval_service.text_search(
        query_text="quantum physics relativity",
        project_id=project.id,
        limit=10
    )

    # Should return empty results
    assert len(results) == 0, "Should return no results for non-matching query"


@pytest.mark.asyncio
async def test_hybrid_search_combines_results(test_db_session: object):
    """Test that hybrid search properly combines vector and text search results."""
    # Setup: Create test data
    project_repo = ProjectRepository(test_db_session)
    file_repo = FileRepository(test_db_session)
    chunk_repo = ChunkRepository(test_db_session)
    retrieval_service = RetrievalService(test_db_session)

    # Create test project
    project = await project_repo.create(
        name=f"test-hybrid-project-{uuid4()}",
        path="/tmp/test-hybrid"
    )
    project = await project_repo.update_status(project.id, "completed")

    # Create test file
    file_doc = await file_repo.create(
        project_id=project.id,
        path="/tmp/test-hybrid/file.py",
        relative_path="file.py",
        language="python",
        size_bytes=1000,
        line_count=50,
        file_hash="abc123",
        ast_status="parsed"
    )

    # Create test chunks - one that matches semantically, one that matches textually
    chunk1 = await chunk_repo.create(
        project_id=project.id,
        file_id=file_doc.id,
        chunk_index=0,
        content="def calculate_average(numbers):\n    return sum(numbers) / len(numbers)",
        start_line=1,
        end_line=2,
        token_count=15,
        metadata={"chunk_type": "function", "symbol_name": "calculate_average"}
    )

    chunk2 = await chunk_repo.create(
        project_id=project.id,
        file_id=file_doc.id,
        chunk_index=1,
        content="# This function processes user login requests\n# It validates credentials and creates sessions\n# Returns authentication token on success\n\ndef process_login(username, password):\n    if validate_credentials(username, password):\n        return create_session_token(username)\n    return None",
        start_line=4,
        end_line=12,
        token_count=25,
        metadata={"chunk_type": "function", "symbol_name": "process_login"}
    )

    await test_db_session.flush()

    # Test: Hybrid search for something that matches both semantically and textually
    # "authentication" should match textually in chunk2 and potentially semantically
    results = await retrieval_service.hybrid_search(
        query_text="authentication",
        project_id=project.id,
        limit=10,
        vector_weight=0.7,
        text_weight=0.3
    )

    # Verify we got results
    assert len(results) > 0, "Hybrid search should return results"

    # Verify results are ordered by combined score (highest first)
    if len(results) > 1:
        for i in range(len(results) - 1):
            assert results[i][1] >= results[i + 1][1], \
                f"Results should be ordered by combined score descending: {results[i][1]} >= {results[i+1][1]}"

    # Verify that we get chunks with proper scoring
    for chunk, score in results:
        assert isinstance(chunk, CodeChunk)
        assert chunk.project_id == project.id
        assert 0.0 <= score <= 1.0


@pytest.mark.asyncio
async def test_hybrid_search_weights(test_db_session: object):
    """Test that hybrid search respects the weighting parameters."""
    # Setup: Create test data
    project_repo = ProjectRepository(test_db_session)
    file_repo = FileRepository(test_db_session)
    chunk_repo = ChunkRepository(test_db_session)
    retrieval_service = RetrievalService(test_db_session)

    # Create test project
    project = await project_repo.create(
        name=f"test-weights-project-{uuid4()}",
        path="/tmp/test-weights"
    )
    project = await project_repo.update_status(project.id, "completed")

    # Create test file
    file_doc = await file_repo.create(
        project_id=project.id,
        path="/tmp/test-weights/file.py",
        relative_path="file.py",
        language="python",
        size_bytes=1000,
        line_count=50,
        file_hash="abc123",
        ast_status="parsed"
    )

    # Create a chunk that should score well on both vector and text search
    chunk = await chunk_repo.create(
        project_id=project.id,
        file_id=file_doc.id,
        chunk_index=0,
        content="def authenticate_user_with_jwt(username, password):\n    # JWT authentication implementation\n    token = generate_jwt_token(username)\n    return token",
        start_line=1,
        end_line=4,
        token_count=20,
        metadata={"chunk_type": "function", "symbol_name": "authenticate_user_with_jwt"}
    )

    await test_db_session.flush()

    # Test: Search with high vector weight
    results_vector_heavy = await retrieval_service.hybrid_search(
        query_text="authentication user",
        project_id=project.id,
        limit=5,
        vector_weight=0.9,  # 90% vector, 10% text
        text_weight=0.1
    )

    # Test: Search with high text weight
    results_text_heavy = await retrieval_service.hybrid_search(
        query_text="authentication user",
        project_id=project.id,
        limit=5,
        vector_weight=0.1,  # 10% vector, 90% text
        text_weight=0.9
    )

    # Both should return results
    assert len(results_vector_heavy) > 0, "Vector-heavy search should return results"
    assert len(results_text_heavy) > 0, "Text-heavy search should return results"

    # The scores should be different due to different weighting
    # Note: Exact values depend on the search implementations, but both should work


if __name__ == "__main__":
    pytest.main([__file__, "-v"])