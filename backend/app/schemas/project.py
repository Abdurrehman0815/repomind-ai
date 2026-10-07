"""
RepoMind AI — Project and File API Schemas
"""
from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field


class ProjectCreateRequest(BaseModel):
    """Payload to import or connect a repository."""
    path: str = Field(..., description="Absolute or relative local path to the repository directory")
    name: str | None = Field(None, description="Optional custom display name for the project")
    settings: dict[str, Any] = Field(default_factory=dict, description="Custom indexing settings and ignore overrides")


class ProjectResponse(BaseModel):
    """Detailed view of an indexed project."""
    id: str
    name: str
    path: str
    status: str
    settings: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    file_count: int = 0
    total_size_bytes: int = 0
    created_at: datetime
    updated_at: datetime


class ProjectListResponse(BaseModel):
    """List response for projects."""
    projects: list[ProjectResponse]
    total: int


class ProjectScanResponse(BaseModel):
    """Result of an incremental or initial repository scan."""
    project_id: str
    status: str
    summary: dict[str, Any]


class FileDocumentResponse(BaseModel):
    """Metadata view of an ingested source file."""
    id: str
    project_id: str
    relative_path: str
    language: str
    size_bytes: int
    line_count: int
    ast_status: str
    file_hash: str
    created_at: datetime


class FileListResponse(BaseModel):
    """List of files inside a project."""
    files: list[FileDocumentResponse]
    total: int
