"""
RepoMind AI — Projects API (Phase 1 Skeleton)

Full CRUD will be implemented in Phase 2+ after database migrations.
This Phase 1 stub returns proper HTTP responses so the frontend and
tests can verify routing works.
"""
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class ProjectListResponse(BaseModel):
    """Response schema for project listing."""
    projects: list[dict]
    total: int


@router.get("", response_model=ProjectListResponse)
async def list_projects() -> ProjectListResponse:
    """
    List all projects.

    Phase 1: Returns empty list — real implementation in Phase 2.
    """
    return ProjectListResponse(projects=[], total=0)
