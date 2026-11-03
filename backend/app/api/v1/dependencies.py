"""
RepoMind AI — Dependencies API

Handles dependency retrieval for projects and files.
"""
from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.db.session import get_db
from app.repositories.dependency_repository import DependencyRepository
from app.repositories.file_repository import FileRepository
from app.repositories.project_repository import ProjectRepository
from app.schemas.dependency import (
    DependencyResponse,
    DependencyListResponse,
)

logger = structlog.get_logger(__name__)
router = APIRouter()


@router.get("/{project_id}/dependencies", response_model=DependencyListResponse)
async def get_project_dependencies(
    project_id: str = Path(..., description="The ID of the project"),
    db: AsyncSession = Depends(get_db),
) -> DependencyListResponse:
    """
    Get all dependencies for a project.
    """
    # Verify project exists
    project_repo = ProjectRepository(db)
    project = await project_repo.get_by_id(project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID '{project_id}' not found.",
        )

    # Get dependencies
    dep_repo = DependencyRepository(db)
    dependencies = await dep_repo.list_by_project(project_id)

    # Convert to response models
    dependency_responses = [
        DependencyResponse(
            id=dep.id,
            project_id=dep.project_id,
            source_file_id=dep.source_file_id,
            target_file_id=dep.target_file_id,
            target_module=dep.target_module,
            import_statement=dep.import_statement,
            symbol_name=dep.symbol_name,
            line_number=dep.line_number,
            created_at=dep.created_at,
        )
        for dep in dependencies
    ]

    return DependencyListResponse(
        dependencies=dependency_responses,
        total=len(dependency_responses),
    )


@router.get("/{project_id}/files/{file_id}/dependencies", response_model=DependencyListResponse)
async def get_file_dependencies(
    project_id: str = Path(..., description="The ID of the project"),
    file_id: str = Path(..., description="The ID of the file"),
    db: AsyncSession = Depends(get_db),
) -> DependencyListResponse:
    """
    Get all dependencies for a specific file within a project.
    """
    # Verify project exists
    project_repo = ProjectRepository(db)
    project = await project_repo.get_by_id(project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID '{project_id}' not found.",
        )

    # Verify file exists and belongs to project
    file_repo = FileRepository(db)
    file_doc = await file_repo.get_by_id(file_id)
    if not file_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File with ID '{file_id}' not found.",
        )

    if file_doc.project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File with ID '{file_id}' does not belong to project '{project_id}'.",
        )

    # Get dependencies for the file
    dep_repo = DependencyRepository(db)
    dependencies = await dep_repo.list_by_file(file_id)

    # Convert to response models
    dependency_responses = [
        DependencyResponse(
            id=dep.id,
            project_id=dep.project_id,
            source_file_id=dep.source_file_id,
            target_file_id=dep.target_file_id,
            target_module=dep.target_module,
            import_statement=dep.import_statement,
            symbol_name=dep.symbol_name,
            line_number=dep.line_number,
            created_at=dep.created_at,
        )
        for dep in dependencies
    ]

    return DependencyListResponse(
        dependencies=dependency_responses,
        total=len(dependency_responses),
    )