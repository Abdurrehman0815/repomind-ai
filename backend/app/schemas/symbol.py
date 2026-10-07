"""
RepoMind AI — Symbol Schemas
"""
from datetime import datetime
from typing import Any
from pydantic import BaseModel


class CodeSymbolResponse(BaseModel):
    """View of an extracted AST symbol."""
    id: str
    project_id: str
    file_id: str
    name: str
    kind: str
    line_start: int
    line_end: int
    signature: str | None = None
    docstring: str | None = None
    parent_symbol_id: str | None = None
    created_at: datetime


class SymbolListResponse(BaseModel):
    """List response for symbols."""
    symbols: list[CodeSymbolResponse]
    total: int


class SymbolParseResponse(BaseModel):
    """Result of triggering AST symbol extraction on a project."""
    project_id: str
    status: str
    stats: dict[str, Any]
