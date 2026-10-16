"""
Tests for Phase 14: Dependency Graph
"""
import tempfile
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.ingestion.service import IngestionService
from app.models.project import Project
from app.models.file_document import FileDocument
from app.models.code_symbol import CodeSymbol
from app.models.code_chunk import CodeChunk
from app.models.dependency import Dependency
from app.repositories.project_repository import ProjectRepository
from app.repositories.file_repository import FileRepository
from app.repositories.symbol_repository import SymbolRepository
from app.repositories.chunk_repository import ChunkRepository
from app.repositories.dependency_repository import DependencyRepository
from app.ingestion.symbol_extractor import SymbolExtractor
from app.ingestion.chunker import Chunker


@pytest.fixture
def db_engine():
    """Create an in-memory SQLite database for testing."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    return engine


@pytest.fixture
async def db_session(db_engine):
    """Create a database session for testing."""
    async with db_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = sessionmaker(
        db_engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session() as session:
        yield session

    await db_engine.dispose()


@pytest.mark.asyncio
async def test_dependency_repository_crud(db_session: AsyncSession):
    """Test basic CRUD operations for DependencyRepository."""
    # Setup
    project_repo = ProjectRepository(db_session)
    file_repo = FileRepository(db_session)
    dep_repo = DependencyRepository(db_session)

    # Create test project
    project = await project_repo.create(
        name="Test Project",
        path="/tmp/test",
        settings={},
    )

    # Create test file
    file_doc = await file_repo.create(
        project_id=project.id,
        path="/tmp/test/main.py",
        relative_path="main.py",
        file_hash="abc123",
        language="python",
        size_bytes=100,
        line_count=10,
    )

    # Test create dependency
    dependency = await dep_repo.create(
        project_id=project.id,
        source_file_id=file_doc.id,
        target_module="os",
        import_statement="import os",
        symbol_name=None,
        line_number=1,
    )

    assert dependency.id is not None
    assert dependency.project_id == project.id
    assert dependency.source_file_id == file_doc.id
    assert dependency.target_module == "os"
    assert dependency.import_statement == "import os"
    assert dependency.symbol_name is None
    assert dependency.line_number == 1

    # Test get by id
    fetched_dep = await dep_repo.get_by_id(dependency.id)
    assert fetched_dep is not None
    assert fetched_dep.id == dependency.id
    assert fetched_dep.target_module == "os"

    # Test list by project
    project_deps = await dep_repo.list_by_project(project.id)
    assert len(project_deps) == 1
    assert project_deps[0].id == dependency.id

    # Test list by file
    file_deps = await dep_repo.list_by_file(file_doc.id)
    assert len(file_deps) == 1
    assert file_deps[0].id == dependency.id

    # Test delete by file
    deleted_count = await dep_repo.delete_by_file(file_doc.id)
    assert deleted_count == 1

    # Verify deletion
    deps_after_delete = await dep_repo.list_by_file(file_doc.id)
    assert len(deps_after_delete) == 0

    # Test delete by project
    # Recreate dependency first
    await dep_repo.create(
        project_id=project.id,
        source_file_id=file_doc.id,
        target_module="sys",
        import_statement="import sys",
        symbol_name=None,
        line_number=2,
    )

    deleted_count = await dep_repo.delete_by_project(project.id)
    assert deleted_count == 1

    # Verify deletion
    deps_after_delete = await dep_repo.list_by_project(project.id)
    assert len(deps_after_delete) == 0


@pytest.mark.asyncio
async def test_symbol_extractor_extracts_dependencies(db_session: AsyncSession):
    """Test that SymbolExtractor correctly extracts and saves dependencies."""
    # Setup
    project_repo = ProjectRepository(db_session)
    file_repo = FileRepository(db_session)
    symbol_repo = SymbolRepository(db_session)
    chunk_repo = ChunkRepository(db_session)
    dep_repo = DependencyRepository(db_session)

    # Create temporary directory and file
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Create test project with path pointing to temp directory
        project = await project_repo.create(
            name="Test Project",
            path=str(temp_path),
            settings={},
        )

        # Create test Python file with imports
        file_content = '''import os
import sys
from typing import List, Dict
from local_module import MyClass

def my_function():
    pass

class MyClass:
    def my_method(self):
        pass
'''

        # Create the actual file on disk
        test_file = temp_path / "main.py"
        test_file.write_text(file_content, encoding="utf-8")

        # Create file document record
        file_doc = await file_repo.create(
            project_id=project.id,
            path=str(test_file),
            relative_path="main.py",
            file_hash="def456",
            language="python",
            size_bytes=len(file_content),
            line_count=len(file_content.splitlines()),
            ast_status="pending",
        )

        # Setup symbol extractor
        symbol_extractor = SymbolExtractor(db_session)

        # Extract symbols (this should also extract dependencies)
        stats = await symbol_extractor.extract_symbols_for_project(project.id)

        # Verify symbols were extracted
        assert stats.files_processed == 1
        assert stats.total_symbols > 0  # Should have functions, classes, methods

        # Verify dependencies were extracted and saved
        dependencies = await dep_repo.list_by_file(file_doc.id)
        assert len(dependencies) == 5  # os, sys, List, Dict, local_module

        # Check specific dependencies
        dep_modules = [dep.target_module for dep in dependencies]
        assert dep_modules.count("os") == 1
        assert dep_modules.count("sys") == 1
        assert dep_modules.count("typing") == 2  # List and Dict are separate dependencies
        assert dep_modules.count("local_module") == 1

        # Check import statements
        import_statements = [dep.import_statement for dep in dependencies]
        assert "import os" in import_statements
        assert "import sys" in import_statements
        assert "from typing import List" in import_statements
        assert "from typing import Dict" in import_statements
        assert "from local_module import MyClass" in import_statements

        # Check line numbers (should be 1, 2, 3, 4 for our imports)
        line_numbers = [dep.line_number for dep in dependencies if dep.line_number is not None]
        assert len(line_numbers) == 5  # All dependencies should have line numbers
        assert 1 in line_numbers  # import os
        assert 2 in line_numbers  # import sys
        assert 3 in line_numbers  # from typing import List, Dict (line 3)
        assert 4 in line_numbers  # from local_module import MyClass

        # Verify file AST status was updated
        await db_session.refresh(file_doc)
        assert file_doc.ast_status == "parsed"


@pytest.mark.asyncio
async def test_dependencies_api_endpoints(db_session: AsyncSession):
    """Test the dependencies API endpoints."""
    from fastapi.testclient import TestClient
    from app.main import create_application
    from app.db.session import get_db

    # Create application
    app = create_application()

    # Override the get_db dependency to use our test session
    async def get_test_db():
        return db_session

    app.dependency_overrides[get_db] = get_test_db

    # Setup
    project_repo = ProjectRepository(db_session)
    file_repo = FileRepository(db_session)
    dep_repo = DependencyRepository(db_session)

    # Create test project
    project = await project_repo.create(
        name="Test Project",
        path="/tmp/test",
        settings={},
    )

    # Create test files
    file1 = await file_repo.create(
        project_id=project.id,
        path="/tmp/test/main.py",
        relative_path="main.py",
        file_hash="abc123",
        language="python",
        size_bytes=100,
        line_count=10,
    )

    file2 = await file_repo.create(
        project_id=project.id,
        path="/tmp/test/utils.py",
        relative_path="utils.py",
        file_hash="def456",
        language="python",
        size_bytes=50,
        line_count=5,
    )

    # Create test dependencies
    await dep_repo.create(
        project_id=project.id,
        source_file_id=file1.id,
        target_module="os",
        import_statement="import os",
        line_number=1,
    )

    await dep_repo.create(
        project_id=project.id,
        source_file_id=file1.id,
        target_module="sys",
        import_statement="import sys",
        line_number=2,
    )

    await dep_repo.create(
        project_id=project.id,
        source_file_id=file2.id,
        target_module="json",
        import_statement="import json",
        line_number=1,
        target_file_id=file1.id,  # Internal dependency
    )

    # Test API endpoints
    client = TestClient(app)

    # Get project dependencies
    response = client.get(f"/api/v1/projects/{project.id}/dependencies")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 3
    assert len(data["dependencies"]) == 3

    # Check that we have the expected dependencies
    dep_modules = [dep["target_module"] for dep in data["dependencies"]]
    assert "os" in dep_modules
    assert "sys" in dep_modules
    assert "json" in dep_modules

    # Get file dependencies for main.py
    response = client.get(f"/api/v1/projects/{project.id}/files/{file1.id}/dependencies")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert len(data["dependencies"]) == 2

    dep_modules = [dep["target_module"] for dep in data["dependencies"]]
    assert "os" in dep_modules
    assert "sys" in dep_modules

    # Get file dependencies for utils.py
    response = client.get(f"/api/v1/projects/{project.id}/files/{file2.id}/dependencies")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert len(data["dependencies"]) == 1
    assert data["dependencies"][0]["target_module"] == "json"
    assert data["dependencies"][0]["target_file_id"] == file1.id  # Internal dependency

    # Test error cases
    # Non-existent project
    response = client.get("/api/v1/projects/non-existent-id/dependencies")
    assert response.status_code == 404

    # Non-existent file
    response = client.get(f"/api/v1/projects/{project.id}/files/non-existent-id/dependencies")
    assert response.status_code == 404

    # File not belonging to project
    # Create another project and file
    project2 = await project_repo.create(
        name="Test Project 2",
        path="/tmp/test2",
        settings={},
    )
    file3 = await file_repo.create(
        project_id=project2.id,
        path="/tmp/test2/other.py",
        relative_path="other.py",
        file_hash="ghi789",
        language="python",
        size_bytes=50,
        line_count=5,
    )

    response = client.get(f"/api/v1/projects/{project.id}/files/{file3.id}/dependencies")
    assert response.status_code == 400  # Bad request - file doesn't belong to project

    # Clean up dependency overrides
    app.dependency_overrides.clear()