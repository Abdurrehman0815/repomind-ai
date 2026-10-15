"""
RepoMind AI — Citation Schema
"""
from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Optional


class CitationBase(BaseModel):
    """Base citation model."""
    file_path: str = Field(..., description="Relative path to the file from repository root")
    start_line: int = Field(..., description="Starting line number (1-indexed)")
    end_line: int = Field(..., description="Ending line number (1-indexed)")
    symbol: Optional[str] = Field(None, description="Symbol name (function, class, etc.) associated with the citation")
    file_hash: str = Field(..., description="Hash of the file content at the time of indexing")
    repository_commit: Optional[str] = Field(None, description="Git commit hash of the repository at the time of indexing")


class CitationCreate(CitationBase):
    """Citation creation model."""
    pass


class CitationResponse(CitationBase):
    """Citation response model."""
    is_stale: bool = Field(False, description="Whether the citation is stale due to file changes")
    repository_id: Optional[str] = Field(None, description="Project ID")

    class Config:
        orm_mode = True