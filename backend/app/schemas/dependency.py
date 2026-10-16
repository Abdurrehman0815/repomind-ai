"""
RepoMind AI — Dependency API Schemas
"""
from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field


class DependencyResponse(BaseModel):
    """Dependency relationship between files or external packages."""
    id: str
    project_id: str
    source_file_id: str
    target_file_id: str | None = Field(None, description="None for external dependencies")
    target_module: str = Field(..., description="Imported module or package name")
    import_statement: str = Field(..., description="Original import statement")
    symbol_name: str | None = Field(None, description="Specific symbol imported, if applicable")
    line_number: int | None = Field(None, description="Line number where import occurs")
    created_at: datetime


class DependencyListResponse(BaseModel):
    """List response for dependencies."""
    dependencies: list[DependencyResponse]
    total: int