"""initial schema with pgvector and code intelligence tables

Revision ID: 001_initial_schema
Revises: 
Create Date: 2026-10-07 21:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import pgvector
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision: str = "001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 0. Enable pgvector extension
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")

    # 1. projects table
    op.create_table(
        "projects",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("path", sa.String(length=1024), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="unindexed"),
        sa.Column("settings", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_projects"),
        sa.UniqueConstraint("path", name="uq_projects_path"),
    )
    op.create_index("ix_projects_name", "projects", ["name"])
    op.create_index("ix_projects_status", "projects", ["status"])

    # 2. file_documents table
    op.create_table(
        "file_documents",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("path", sa.String(length=1024), nullable=False),
        sa.Column("relative_path", sa.String(length=1024), nullable=False),
        sa.Column("file_hash", sa.String(length=64), nullable=False),
        sa.Column("language", sa.String(length=50), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("line_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ast_status", sa.String(length=50), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], name="fk_file_documents_project_id_projects", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_file_documents"),
    )
    op.create_index("ix_file_documents_project_id", "file_documents", ["project_id"])
    op.create_index("ix_file_documents_relative_path", "file_documents", ["relative_path"])
    op.create_index("ix_file_documents_file_hash", "file_documents", ["file_hash"])
    op.create_index("ix_file_documents_language", "file_documents", ["language"])

    # 3. code_symbols table
    op.create_table(
        "code_symbols",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("file_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("kind", sa.String(length=50), nullable=False),
        sa.Column("line_start", sa.Integer(), nullable=False),
        sa.Column("line_end", sa.Integer(), nullable=False),
        sa.Column("signature", sa.Text(), nullable=True),
        sa.Column("docstring", sa.Text(), nullable=True),
        sa.Column("parent_symbol_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], name="fk_code_symbols_project_id_projects", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["file_id"], ["file_documents.id"], name="fk_code_symbols_file_id_file_documents", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_symbol_id"], ["code_symbols.id"], name="fk_code_symbols_parent_symbol_id_code_symbols", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_code_symbols"),
    )
    op.create_index("ix_code_symbols_project_id", "code_symbols", ["project_id"])
    op.create_index("ix_code_symbols_file_id", "code_symbols", ["file_id"])
    op.create_index("ix_code_symbols_name", "code_symbols", ["name"])
    op.create_index("ix_code_symbols_kind", "code_symbols", ["kind"])
    op.create_index("ix_code_symbols_parent_symbol_id", "code_symbols", ["parent_symbol_id"])

    # 4. code_chunks table with pgvector Vector(768)
    op.create_table(
        "code_chunks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("file_id", sa.String(length=36), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("start_line", sa.Integer(), nullable=False),
        sa.Column("end_line", sa.Integer(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("embedding", Vector(768), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], name="fk_code_chunks_project_id_projects", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["file_id"], ["file_documents.id"], name="fk_code_chunks_file_id_file_documents", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_code_chunks"),
    )
    op.create_index("ix_code_chunks_project_id", "code_chunks", ["project_id"])
    op.create_index("ix_code_chunks_file_id", "code_chunks", ["file_id"])

    # HNSW vector index for fast similarity search
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_code_chunks_embedding_hnsw "
        "ON code_chunks USING hnsw (embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64);"
    )

    # 5. dependencies table
    op.create_table(
        "dependencies",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("source_file_id", sa.String(length=36), nullable=False),
        sa.Column("target_file_id", sa.String(length=36), nullable=True),
        sa.Column("target_module", sa.String(length=512), nullable=False),
        sa.Column("import_statement", sa.Text(), nullable=False),
        sa.Column("symbol_name", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], name="fk_dependencies_project_id_projects", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_file_id"], ["file_documents.id"], name="fk_dependencies_source_file_id_file_documents", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_file_id"], ["file_documents.id"], name="fk_dependencies_target_file_id_file_documents", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_dependencies"),
    )
    op.create_index("ix_dependencies_project_id", "dependencies", ["project_id"])
    op.create_index("ix_dependencies_source_file_id", "dependencies", ["source_file_id"])
    op.create_index("ix_dependencies_target_file_id", "dependencies", ["target_file_id"])

    # 6. chat_sessions table
    op.create_table(
        "chat_sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False, server_default="New Conversation"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], name="fk_chat_sessions_project_id_projects", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_chat_sessions"),
    )
    op.create_index("ix_chat_sessions_project_id", "chat_sessions", ["project_id"])

    # 7. chat_messages table
    op.create_table(
        "chat_messages",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("role", sa.String(length=50), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("citations", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("reasoning_trace", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["chat_sessions.id"], name="fk_chat_messages_session_id_chat_sessions", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_chat_messages"),
    )
    op.create_index("ix_chat_messages_session_id", "chat_messages", ["session_id"])
    op.create_index("ix_chat_messages_role", "chat_messages", ["role"])

    # 8. evaluation_feedbacks table
    op.create_table(
        "evaluation_feedbacks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("message_id", sa.String(length=36), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("feedback_text", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["message_id"], ["chat_messages.id"], name="fk_evaluation_feedbacks_message_id_chat_messages", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_evaluation_feedbacks"),
    )
    op.create_index("ix_evaluation_feedbacks_message_id", "evaluation_feedbacks", ["message_id"])


def downgrade() -> None:
    op.drop_table("evaluation_feedbacks")
    op.drop_table("chat_messages")
    op.drop_table("chat_sessions")
    op.drop_table("dependencies")
    op.drop_table("code_chunks")
    op.drop_table("code_symbols")
    op.drop_table("file_documents")
    op.drop_table("projects")
