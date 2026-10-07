"""
RepoMind AI — Symbol Extraction Orchestrator

Iterates over ingested file documents, invokes language parsers, resolves
hierarchical parent-child symbol relationships, and persists extracted AST symbols.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.parsers import parse_file_content
from app.models.file_document import FileDocument
from app.models.code_symbol import CodeSymbol
from app.repositories.file_repository import FileRepository
from app.repositories.symbol_repository import SymbolRepository

logger = structlog.get_logger(__name__)


class SymbolExtractionStats:
    """Summary of symbol extraction pass."""

    def __init__(self, project_id: str) -> None:
        self.project_id = project_id
        self.files_processed: int = 0
        self.total_symbols: int = 0
        self.symbols_by_kind: dict[str, int] = {}
        self.files_with_errors: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "files_processed": self.files_processed,
            "total_symbols": self.total_symbols,
            "symbols_by_kind": self.symbols_by_kind,
            "files_with_errors": self.files_with_errors,
        }


class SymbolExtractor:
    """Coordinates parsing across all files in a project."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.file_repo = FileRepository(session)
        self.symbol_repo = SymbolRepository(session)

    async def extract_symbols_for_project(
        self, project_id: str
    ) -> SymbolExtractionStats:
        """Parse all pending/unparsed files in a project."""
        stats = SymbolExtractionStats(project_id)
        files = await self.file_repo.list_by_project(project_id)

        for doc in files:
            symbols = await self.extract_symbols_for_file(doc)
            stats.files_processed += 1
            stats.total_symbols += len(symbols)
            for s in symbols:
                stats.symbols_by_kind[s.kind] = (
                    stats.symbols_by_kind.get(s.kind, 0) + 1
                )
            if doc.ast_status in {"error", "partial"}:
                stats.files_with_errors += 1

        await self.session.flush()
        return stats

    async def extract_symbols_for_file(
        self, doc: FileDocument
    ) -> list[CodeSymbol]:
        """Parse a single source file and persist its symbols with parent-child links."""
        file_path = Path(doc.path)
        if not file_path.exists():
            doc.ast_status = "error"
            return []

        # Read file contents safely
        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            logger.warning("failed_to_read_source_file", path=doc.path, error=str(exc))
            doc.ast_status = "error"
            return []

        # Parse AST
        result = parse_file_content(doc.language, content, file_path=doc.path)

        # Clear existing symbols for this file to ensure idempotency
        await self.symbol_repo.delete_by_file(doc.id)

        # First pass: Create parent symbols (classes, interfaces)
        created_symbols: list[CodeSymbol] = []
        parent_map: dict[str, str] = {}  # parent_name -> parent_symbol_id

        # Sort so that items without parent_name are created first
        parents = [s for s in result.symbols if not s.parent_name]
        children = [s for s in result.symbols if s.parent_name]

        for s in parents:
            sym = await self.symbol_repo.create(
                project_id=doc.project_id,
                file_id=doc.id,
                name=s.name,
                kind=s.kind,
                line_start=s.line_start,
                line_end=s.line_end,
                signature=s.signature,
                docstring=s.docstring,
                parent_symbol_id=None,
            )
            created_symbols.append(sym)
            parent_map[s.name] = sym.id

        # Second pass: Create children (methods) linked to parent_symbol_id
        for s in children:
            parent_id = parent_map.get(s.parent_name) if s.parent_name else None
            sym = await self.symbol_repo.create(
                project_id=doc.project_id,
                file_id=doc.id,
                name=s.name,
                kind=s.kind,
                line_start=s.line_start,
                line_end=s.line_end,
                signature=s.signature,
                docstring=s.docstring,
                parent_symbol_id=parent_id,
            )
            created_symbols.append(sym)

        # Update file AST status
        doc.ast_status = result.status
        return created_symbols
