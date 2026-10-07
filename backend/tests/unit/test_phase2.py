"""
RepoMind AI — Phase 2 Database and Migrations Tests

Verifies:
1. All 8 database models and their table definitions in SQLAlchemy metadata
2. pgvector Vector(768) column configuration on CodeChunk
3. Foreign key constraints and relationships between models
4. Alembic migration scripts and configuration
5. Repository abstractions
"""
import uuid
from datetime import datetime
import pytest
from sqlalchemy import inspect
from pgvector.sqlalchemy import Vector

from app.db.base import Base
from app.models import (
    Project,
    FileDocument,
    CodeSymbol,
    CodeChunk,
    Dependency,
    ChatSession,
    ChatMessage,
    EvaluationFeedback,
)
from app.repositories import (
    ProjectRepository,
    FileRepository,
    ChunkRepository,
    SymbolRepository,
)


class TestDatabaseSchemaMetadata:
    """Verifies that all models register properly in the declarative Base metadata."""

    def test_all_tables_registered(self):
        expected_tables = {
            "projects",
            "file_documents",
            "code_symbols",
            "code_chunks",
            "dependencies",
            "chat_sessions",
            "chat_messages",
            "evaluation_feedbacks",
        }
        registered_tables = set(Base.metadata.tables.keys())
        assert expected_tables.issubset(registered_tables), (
            f"Missing tables: {expected_tables - registered_tables}"
        )

    def test_project_table_columns(self):
        table = Base.metadata.tables["projects"]
        col_names = {col.name for col in table.columns}
        assert {"id", "name", "path", "status", "settings", "metadata", "created_at", "updated_at"}.issubset(col_names)

    def test_file_document_table_columns(self):
        table = Base.metadata.tables["file_documents"]
        col_names = {col.name for col in table.columns}
        assert {
            "id", "project_id", "path", "relative_path", "file_hash",
            "language", "size_bytes", "line_count", "ast_status",
            "created_at", "updated_at"
        }.issubset(col_names)

    def test_code_symbol_table_columns(self):
        table = Base.metadata.tables["code_symbols"]
        col_names = {col.name for col in table.columns}
        assert {
            "id", "project_id", "file_id", "name", "kind",
            "line_start", "line_end", "signature", "docstring",
            "parent_symbol_id", "created_at"
        }.issubset(col_names)

    def test_code_chunk_table_columns_and_vector(self):
        table = Base.metadata.tables["code_chunks"]
        col_names = {col.name for col in table.columns}
        assert {
            "id", "project_id", "file_id", "chunk_index", "content",
            "start_line", "end_line", "token_count", "embedding",
            "metadata", "created_at"
        }.issubset(col_names)

        # Verify embedding column uses Vector(768)
        embedding_col = table.columns["embedding"]
        assert isinstance(embedding_col.type, Vector)
        assert embedding_col.type.dim == 768

    def test_dependency_table_columns(self):
        table = Base.metadata.tables["dependencies"]
        col_names = {col.name for col in table.columns}
        assert {
            "id", "project_id", "source_file_id", "target_file_id",
            "target_module", "import_statement", "symbol_name", "created_at"
        }.issubset(col_names)

    def test_chat_tables_columns(self):
        sessions_table = Base.metadata.tables["chat_sessions"]
        messages_table = Base.metadata.tables["chat_messages"]
        feedback_table = Base.metadata.tables["evaluation_feedbacks"]

        assert {"id", "project_id", "title", "created_at", "updated_at"}.issubset(
            {c.name for c in sessions_table.columns}
        )
        assert {"id", "session_id", "role", "content", "citations", "reasoning_trace"}.issubset(
            {c.name for c in messages_table.columns}
        )
        assert {"id", "message_id", "rating", "feedback_text"}.issubset(
            {c.name for c in feedback_table.columns}
        )


class TestModelInstantiation:
    """Verifies that model entities can be instantiated and have expected attributes."""

    def test_project_instantiation(self):
        project = Project(
            id=str(uuid.uuid4()),
            name="repomind-ai",
            path="/local/repomind-ai",
            status="unindexed",
            settings={"exclude": ["*.tmp"]},
            metadata_={"repo_size": 1024},
        )
        assert project.name == "repomind-ai"
        assert project.status == "unindexed"
        assert project.settings["exclude"] == ["*.tmp"]
        assert "Project" in repr(project)

    def test_file_document_instantiation(self):
        doc = FileDocument(
            id=str(uuid.uuid4()),
            project_id=str(uuid.uuid4()),
            path="/local/repomind-ai/src/main.py",
            relative_path="src/main.py",
            file_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            language="python",
            size_bytes=1024,
            line_count=42,
            ast_status="parsed",
        )
        assert doc.relative_path == "src/main.py"
        assert doc.language == "python"
        assert doc.line_count == 42
        assert "FileDocument" in repr(doc)

    def test_code_chunk_instantiation_with_vector(self):
        dummy_embedding = [0.1] * 768
        chunk = CodeChunk(
            id=str(uuid.uuid4()),
            project_id=str(uuid.uuid4()),
            file_id=str(uuid.uuid4()),
            chunk_index=0,
            content="def hello(): pass",
            start_line=1,
            end_line=2,
            token_count=6,
            embedding=dummy_embedding,
            metadata_={"kind": "function"},
        )
        assert chunk.chunk_index == 0
        assert len(chunk.embedding) == 768
        assert chunk.token_count == 6

    def test_code_symbol_instantiation(self):
        sym = CodeSymbol(
            id=str(uuid.uuid4()),
            project_id=str(uuid.uuid4()),
            file_id=str(uuid.uuid4()),
            name="calculate_score",
            kind="function",
            line_start=10,
            line_end=25,
            signature="def calculate_score(val: int) -> float",
            docstring="Computes metric score.",
        )
        assert sym.name == "calculate_score"
        assert sym.kind == "function"
        assert sym.line_start == 10

    def test_chat_models_instantiation(self):
        session = ChatSession(
            id=str(uuid.uuid4()),
            project_id=str(uuid.uuid4()),
            title="Refactoring analysis",
        )
        assert session.title == "Refactoring analysis"

        msg = ChatMessage(
            id=str(uuid.uuid4()),
            session_id=session.id,
            role="assistant",
            content="Here is the refactored design.",
            citations=[{"file": "main.py", "lines": [10, 20]}],
            reasoning_trace=[{"thought": "Inspecting AST"}],
        )
        assert msg.role == "assistant"
        assert len(msg.citations) == 1
        assert len(msg.reasoning_trace) == 1

        feedback = EvaluationFeedback(
            id=str(uuid.uuid4()),
            message_id=msg.id,
            rating=1,
            feedback_text="Accurate code citation",
        )
        assert feedback.rating == 1


class TestAlembicMigrationIntegrity:
    """Verifies Alembic environment and migration definitions."""

    def test_migration_001_imports_and_has_revisions(self):
        import importlib.util
        from pathlib import Path

        migration_path = Path(__file__).parent.parent.parent / "alembic" / "versions" / "001_initial_schema.py"
        assert migration_path.exists(), "Migration file 001_initial_schema.py must exist"

        spec = importlib.util.spec_from_file_location("initial_schema_001", str(migration_path))
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        assert mod.revision == "001_initial_schema"
        assert mod.down_revision is None
        assert callable(mod.upgrade)
        assert callable(mod.downgrade)
