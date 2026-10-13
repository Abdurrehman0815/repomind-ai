"""
RepoMind AI — Phase 5 Code Chunking Tests

Tests:
1. Chunker service: logical chunking strategy implementation
2. Chunk boundary validation and line range correctness
3. Metadata population and chunk type prioritization
4. Oversized function splitting and duplicate prevention
5. Fallback line-based chunking and module section chunking
6. Integration with SymbolExtractor and chunk persistence
"""
from __future__ import annotations

import tempfile
from pathlib import Path
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from app.ingestion.chunker import Chunker
from app.ingestion.symbol_extractor import SymbolExtractor
from app.models.code_chunk import CodeChunk
from app.models.code_symbol import CodeSymbol
from app.models.file_document import FileDocument
from app.models.project import Project
from app.repositories.chunk_repository import ChunkRepository
from app.repositories.file_repository import FileRepository
from app.repositories.project_repository import ProjectRepository
from app.repositories.symbol_repository import SymbolRepository
from app.db.base import Base


# Test database URL for SQLite (for testing purposes)
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture
async def db_session():
    """Create a test database session."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session_maker = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session_maker() as session:
        yield session

    await engine.dispose()


@pytest.fixture
def sample_python_file():
    """Create a sample Python file for testing."""
    return tempfile.NamedTemporaryFile(
        mode='w',
        suffix='.py',
        delete=False,
        encoding='utf-8'
    )


class TestChunkerService:
    """Tests the Chunker service logical chunking strategy."""

    def setup_method(self):
        self.chunker = Chunker(max_tokens_per_chunk=100)  # Small limit for testing

    def test_count_tokens(self):
        """Test token counting functionality."""
        text = "Hello world"
        count = self.chunker.count_tokens(text)
        assert isinstance(count, int)
        assert count > 0

    def test_create_symbol_chunk_function(self):
        """Test creating a chunk from a function symbol."""
        lines = [
            "def hello_world():",
            "    \"\"\"Say hello to the world.\"\"\"",
            "    print('Hello, World!')",
            "    return True"
        ]
        content = "\n".join(lines)

        # Mock symbol
        from app.models.code_symbol import CodeSymbol
        symbol = CodeSymbol(
            id="test-symbol-id",
            project_id="test-project",
            file_id="test-file",
            name="hello_world",
            kind="function",
            line_start=1,
            line_end=4,
            signature="def hello_world():",
            docstring="Say hello to the world.",
            parent_symbol_id=None,
            metadata={}
        )

        chunk_data = self.chunker._create_symbol_chunk(symbol, lines, content, "function")

        assert chunk_data is not None
        assert chunk_data.content == content
        assert chunk_data.start_line == 1
        assert chunk_data.end_line == 4
        assert chunk_data.chunk_type == "function"
        assert chunk_data.symbol_name == "hello_world"
        assert chunk_data.metadata["symbol_name"] == "hello_world"
        assert chunk_data.metadata["symbol_kind"] == "function"
        assert chunk_data.metadata["has_docstring"] is True

    def test_create_symbol_chunk_class(self):
        """Test creating a chunk from a class symbol."""
        lines = [
            "class Calculator:",
            "    \"\"\"Performs calculations.\"\"\"",
            "    def add(self, a, b):",
            "        return a + b",
            "",
            "    def multiply(self, a, b):",
            "        return a * b"
        ]
        content = "\n".join(lines)

        # Mock symbol
        symbol = CodeSymbol(
            id="test-symbol-id",
            project_id="test-project",
            file_id="test-file",
            name="Calculator",
            kind="class",
            line_start=1,
            line_end=7,
            signature=None,
            docstring="Performs calculations.",
            parent_symbol_id=None,
            metadata={}
        )

        chunk_data = self.chunker._create_symbol_chunk(symbol, lines, content, "class")

        assert chunk_data is not None
        assert chunk_data.content == content
        assert chunk_data.start_line == 1
        assert chunk_data.end_line == 7
        assert chunk_data.chunk_type == "class"
        assert chunk_data.symbol_name == "Calculator"

    def test_create_symbol_chunk_method(self):
        """Test creating a chunk from a method symbol."""
        lines = [
            "class Calculator:",
            "    def add(self, a, b):",
            "        \"\"\"Add two numbers.\"\"\"",
            "        return a + b",
            "",
            "    def multiply(self, a, b):",
            "        return a * b"
        ]
        content = "\n".join(lines)

        # Mock symbol for method
        # First create a parent class symbol
        parent_symbol = CodeSymbol(
            id="parent-symbol-id",
            project_id="test-project",
            file_id="test-file",
            name="Calculator",
            kind="class",
            line_start=1,
            line_end=6,
            signature=None,
            docstring=None,
            parent_symbol_id=None,
            metadata={}
        )
        # Create method symbol with parent reference
        symbol = CodeSymbol(
            id="test-symbol-id",
            project_id="test-project",
            file_id="test-file",
            name="add",
            kind="method",
            line_start=2,
            line_end=4,
            signature="def add(self, a, b):",
            docstring="Add two numbers.",
            parent_symbol_id=parent_symbol.id,
            metadata={}
        )

        chunk_data = self.chunker._create_symbol_chunk(symbol, lines, content, "method")

        assert chunk_data is not None
        assert chunk_data.start_line == 2
        assert chunk_data.end_line == 4
        assert chunk_data.chunk_type == "method"
        assert chunk_data.symbol_name == "add"
        assert chunk_data.metadata["parent_symbol_id"] is not None

    def test_create_symbol_chunk_invalid_line_ranges(self):
        """Test that invalid line ranges are rejected."""
        lines = ["line 1", "line 2", "line 3"]
        content = "\n".join(lines)

        # Mock symbol with invalid line range
        symbol = CodeSymbol(
            id="test-symbol-id",
            project_id="test-project",
            file_id="test-file",
            name="test_func",
            kind="function",
            line_start=5,  # Beyond file length
            line_end=10,
            signature=None,
            docstring=None,
            metadata={}
        )

        chunk_data = self.chunker._create_symbol_chunk(symbol, lines, content, "function")
        assert chunk_data is None  # Should reject invalid range

    def test_is_valid_chunk_no_overlap(self):
        """Test chunk validation with no overlap."""
        processed_ranges = {(5, 10), (20, 25)}

        # Valid chunk - no overlap
        chunk1 = type('ChunkData', (), {
            'start_line': 1,
            'end_line': 3,
            'metadata': {}
        })()

        assert self.chunker._is_valid_chunk(chunk1, processed_ranges) is True

    def test_is_valid_chunk_with_overlap(self):
        """Test chunk validation detects significant overlap."""
        processed_ranges = {(5, 10)}

        # Chunk with significant overlap
        chunk1 = type('ChunkData', (), {
            'start_line': 7,
            'end_line': 12,  # Overlaps 7-10 with processed range
            'metadata': {}
        })()

        # Should reject due to >50% overlap
        assert self.chunker._is_valid_chunk(chunk1, processed_ranges) is False

    def test_has_uncovered_content(self):
        """Test detection of uncovered content."""
        lines = ["line 1", "line 2", "line 3", "line 4", "line 5"]
        processed_ranges = {(2, 3)}  # Only covers lines 2-3

        assert self.chunker._has_uncovered_content(lines, processed_ranges) is True

    def test_all_content_covered(self):
        """Test when all content is already covered."""
        lines = ["line 1", "line 2", "line 3"]
        processed_ranges = {(1, 3)}  # Covers all lines

        assert self.chunker._has_uncovered_content(lines, processed_ranges) is False

    def test_split_large_content(self):
        """Test splitting large content into smaller chunks."""
        # Create content that exceeds token limit
        lines = [f"def function_{i}():" + "\n    pass" for i in range(20)]
        content = "\n\n".join(lines)

        chunks = self.chunker._split_large_content(content, 1, len(lines), "test_type")

        assert len(chunks) > 1
        for chunk in chunks:
            assert self.chunker.count_tokens(chunk.content) <= self.chunker.max_tokens_per_chunk
            assert chunk.chunk_type == "test_type_split"
            assert chunk.metadata["is_split"] is True

    def test_create_module_section_chunks(self):
        """Test creating chunks for module-level code."""
        lines = [
            "# Module level comment",
            "import os",
            "",
            "CONSTANT = 42",
            "",
            "def main():",
            "    pass",
            "",
            "# Another module section",
            "another_var = 'hello'"
        ]
        content = "\n".join(lines)
        processed_ranges = {(6, 8)}  # Only the main function is processed

        chunks = self.chunker._create_module_section_chunks(lines, content, processed_ranges)

        # Should create chunks for the uncovered sections
        assert len(chunks) >= 2  # Import section and final section

        # Check that chunks are valid
        for chunk in chunks:
            assert chunk.start_line >= 1
            assert chunk.end_line <= len(lines)
            assert chunk.start_line <= chunk.end_line
            assert chunk.content.strip()  # Should have actual content

    def test_create_line_based_chunks(self):
        """Test fallback line-based chunking."""
        lines = [
            "# Comment only file",
            "# Another comment",
            "",
            "# Final comment"
        ]
        content = "\n".join(lines)
        processed_ranges = set()  # No symbols processed

        chunks = self.chunker._create_line_based_chunks(lines, content, processed_ranges)

        assert len(chunks) >= 1
        for chunk in chunks:
            assert chunk.chunk_type == "line_based"
            assert chunk.metadata["is_fallback"] is True

    def test_chunk_file_simple(self):
        """Test chunking a simple file with functions."""
        lines = [
            "def hello():",
            "    print('Hello')",
            "",
            "def world():",
            "    print('World')",
            "",
            "if __name__ == '__main__':",
            "    hello()",
            "    world()"
        ]
        content = "\n".join(lines)

        # Mock symbols
        symbols = [
            CodeSymbol(
                id="sym1",
                project_id="test",
                file_id="test",
                name="hello",
                kind="function",
                line_start=1,
                line_end=2,
                signature=None,
                docstring=None,
                parent_symbol_id=None,
                metadata={}
            ),
            CodeSymbol(
                id="sym2",
                project_id="test",
                file_id="test",
                name="world",
                kind="function",
                line_start=4,
                line_end=5,
                signature=None,
                docstring=None,
                parent_symbol_id=None,
                metadata={}
            )
        ]

        chunks = self.chunker.chunk_file(
            type('FileDoc', (), {
                'path': ':memory:',
                'id': 'test-file'
            })(),
            symbols,
            content
        )

        assert len(chunks) >= 2  # At least the two functions
        # Check that we have function chunks
        function_chunks = [c for c in chunks if c.chunk_type == "function"]
        assert len(function_chunks) == 2

    def test_chunk_file_oversized_function(self):
        """Test that oversized functions are split safely."""
        # Create a large function that exceeds token limit
        large_function_lines = [
            "def large_function():",
            "    \"\"\"A very large function that should be split.\"\"\""
        ]
        # Add many lines to make it oversized
        for i in range(50):
            large_function_lines.append(f"    line_{i} = '{'x' * 50}'")
        large_function_lines.extend([
            "    result = sum(range(1000))",
            "    return result"
        ])

        lines = large_function_lines
        content = "\n".join(lines)

        # Mock symbol for the large function
        symbols = [
            CodeSymbol(
                id="sym1",
                project_id="test",
                file_id="test",
                name="large_function",
                kind="function",
                line_start=1,
                line_end=len(lines),
                signature=None,
                docstring="A very large function that should be split.",
                parent_symbol_id=None,
                metadata={}
            )
        ]

        chunks = self.chunker.chunk_file(
            type('FileDoc', (), {
                'path': ':memory:',
                'id': 'test-file'
            })(),
            symbols,
            content
        )

        # Should have multiple chunks due to splitting
        assert len(chunks) > 1
        # Each chunk should be within token limit
        for chunk in chunks:
            assert self.chunker.count_tokens(chunk.content) <= self.chunker.max_tokens_per_chunk
            # Should indicate it's a split chunk
            assert "split" in chunk.chunk_type or "_part_" in chunk.chunk_type


class TestSymbolExtractorWithChunking:
    """Test integration of chunking with SymbolExtractor."""

    @pytest.mark.asyncio
    async def test_symbol_extractor_creates_chunks(self, db_session: AsyncSession):
        """Test that SymbolExtractor creates chunks after extracting symbols."""
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_dir = Path(temp_dir) / "test_repo"
            repo_dir.mkdir()

            # Create a test Python file
            test_file = repo_dir / "sample.py"
            test_file.write_text(
                '''
def hello_world():
    """Simple greeting function."""
    print("Hello, World!")
    return True

class Calculator:
    """A simple calculator class."""

    def add(self, a, b):
        """Add two numbers."""
        return a + b

    def multiply(self, a, b):
        """Multiply two numbers."""
        return a * b

def main():
    """Main entry point."""
    calc = Calculator()
    result = calc.add(5, 3)
    print(f"5 + 3 = {result}")

if __name__ == "__main__":
    main()
                ''',
                encoding="utf-8"
            )

            # 1. Ingest repository
            from app.ingestion.service import IngestionService
            ingestion_service = IngestionService(db_session)
            project, _ = await ingestion_service.import_repository(str(repo_dir), name="Chunking Test")

            # 2. Extract symbols (should also create chunks)
            extractor = SymbolExtractor(db_session)
            stats = await extractor.extract_symbols_for_project(project.id)

            # Verify symbol extraction worked
            assert stats.files_processed == 1
            assert stats.total_symbols >= 4  # hello_world, Calculator, add, multiply, main

            # 3. Verify chunks were created
            chunk_repo = ChunkRepository(db_session)
            chunks = await chunk_repo.list_by_project(project.id)

            assert len(chunks) > 0, "Should have created chunks for the file"

            # Verify chunk properties
            for chunk in chunks:
                assert chunk.project_id == project.id
                assert chunk.content.strip()  # Should have actual content
                assert chunk.start_line >= 1
                assert chunk.end_line >= chunk.start_line
                assert chunk.token_count >= 0

                # Verify metadata is present
                assert isinstance(chunk.metadata_, dict)
                assert "chunk_type" in chunk.metadata_ or "chunk_index" in chunk.metadata_

    @pytest.mark.asyncio
    async def test_chunk_persistence_and_retrieval(self, db_session: AsyncSession):
        """Test that chunks can be persisted and retrieved correctly."""
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_dir = Path(temp_dir) / "test_repo"
            repo_dir.mkdir()

            # Create a test file
            test_file = repo_dir / "simple.py"
            test_file.write_text(
                '''
def test_function():
    """A test function."""
    x = 1
    y = 2
    return x + y

CONSTANT_VALUE = 42

class TestClass:
    """A test class."""
    pass
                ''',
                encoding="utf-8"
            )

            # Ingest and extract
            from app.ingestion.service import IngestionService
            ingestion_service = IngestionService(db_session)
            project, _ = await ingestion_service.import_repository(str(repo_dir), name="Persistence Test")

            extractor = SymbolExtractor(db_session)
            await extractor.extract_symbols_for_project(project.id)

            # Retrieve chunks
            chunk_repo = ChunkRepository(db_session)
            file_repo = FileRepository(db_session)

            files = await file_repo.list_by_project(project.id)
            assert len(files) == 1

            file_chunks = await chunk_repo.list_by_file(files[0].id)
            assert len(file_chunks) > 0

            # Test getting chunk by ID
            first_chunk = file_chunks[0]
            retrieved_chunk = await chunk_repo.get_by_id(first_chunk.id)
            assert retrieved_chunk is not None
            assert retrieved_chunk.id == first_chunk.id
            assert retrieved_chunk.content == first_chunk.content

            # Test deleting chunks by file
            deleted_count = await chunk_repo.delete_by_file(files[0].id)
            assert deleted_count == len(file_chunks)

            # Verify chunks are gone
            remaining_chunks = await chunk_repo.list_by_file(files[0].id)
            assert len(remaining_chunks) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])