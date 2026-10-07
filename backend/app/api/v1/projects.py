"""
RepoMind AI — Projects & Repository Management API

Handles repository registration, file inspection, incremental scanning,
and project lifecycle management.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.db.session import get_db
from app.ingestion.service import IngestionService, RepositoryValidationError
from app.repositories.project_repository import ProjectRepository
from app.repositories.file_repository import FileRepository
from app.schemas.project import (
    ProjectCreateRequest,
    ProjectResponse,
    ProjectListResponse,
    ProjectScanResponse,
    FileDocumentResponse,
    FileListResponse,
)

logger = structlog.get_logger(__name__)
router = APIRouter()


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    payload: ProjectCreateRequest,
    db: AsyncSession = Depends(get_db),
) -> ProjectResponse:
    """
    Import and register a local software repository.
    Validates path, runs initial file scanner, and persists file documents.
    """
    service = IngestionService(db)
    try:
        project, summary = await service.import_repository(
            path=payload.path,
            name=payload.name,
            settings=payload.settings,
        )
    except RepositoryValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    except Exception as exc:
        logger.error("failed_to_import_project", path=payload.path, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to import repository: {exc}",
        )

    file_repo = FileRepository(db)
    files = await file_repo.list_by_project(project.id)
    total_size = sum(f.size_bytes for f in files)

    return ProjectResponse(
        id=project.id,
        name=project.name,
        path=project.path,
        status=project.status,
        settings=project.settings,
        metadata=project.metadata_,
        file_count=len(files),
        total_size_bytes=total_size,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


@router.get("", response_model=ProjectListResponse)
async def list_projects(
    db: AsyncSession = Depends(get_db),
) -> ProjectListResponse:
    """
    List all registered repositories with file and size statistics.
    """
    project_repo = ProjectRepository(db)
    file_repo = FileRepository(db)

    try:
        projects = await project_repo.list_all()
    except Exception as exc:
        logger.warning("database_offline_returning_empty_projects", error=str(exc))
        return ProjectListResponse(projects=[], total=0)

    project_responses: list[ProjectResponse] = []

    for proj in projects:
        try:
            files = await file_repo.list_by_project(proj.id)
            total_size = sum(f.size_bytes for f in files)
        except Exception:
            files = []
            total_size = 0

        project_responses.append(
            ProjectResponse(
                id=proj.id,
                name=proj.name,
                path=proj.path,
                status=proj.status,
                settings=proj.settings,
                metadata=proj.metadata_,
                file_count=len(files),
                total_size_bytes=total_size,
                created_at=proj.created_at,
                updated_at=proj.updated_at,
            )
        )

    return ProjectListResponse(
        projects=project_responses,
        total=len(project_responses),
    )


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: str,
    db: AsyncSession = Depends(get_db),
) -> ProjectResponse:
    """
    Get detailed information for a single project.
    """
    project_repo = ProjectRepository(db)
    file_repo = FileRepository(db)

    proj = await project_repo.get_by_id(project_id)
    if not proj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID '{project_id}' not found.",
        )

    files = await file_repo.list_by_project(proj.id)
    total_size = sum(f.size_bytes for f in files)

    return ProjectResponse(
        id=proj.id,
        name=proj.name,
        path=proj.path,
        status=proj.status,
        settings=proj.settings,
        metadata=proj.metadata_,
        file_count=len(files),
        total_size_bytes=total_size,
        created_at=proj.created_at,
        updated_at=proj.updated_at,
    )


@router.post("/{project_id}/scan", response_model=ProjectScanResponse)
async def scan_project(
    project_id: str,
    db: AsyncSession = Depends(get_db),
) -> ProjectScanResponse:
    """
    Trigger an incremental file scan on an existing repository.
    Detects added, modified, unchanged, and deleted source files.
    """
    project_repo = ProjectRepository(db)
    proj = await project_repo.get_by_id(project_id)
    if not proj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID '{project_id}' not found.",
        )

    service = IngestionService(db)
    try:
        summary = await service.sync_files(proj)
    except Exception as exc:
        logger.error("scan_project_failed", project_id=project_id, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Incremental scan failed: {exc}",
        )

    return ProjectScanResponse(
        project_id=proj.id,
        status=proj.status,
        summary=summary.to_dict(),
    )


@router.get("/{project_id}/files", response_model=FileListResponse)
async def list_project_files(
    project_id: str,
    db: AsyncSession = Depends(get_db),
) -> FileListResponse:
    """
    List all ingested source files within a project.
    """
    project_repo = ProjectRepository(db)
    proj = await project_repo.get_by_id(project_id)
    if not proj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID '{project_id}' not found.",
        )

    file_repo = FileRepository(db)
    files = await file_repo.list_by_project(project_id)

    return FileListResponse(
        files=[
            FileDocumentResponse(
                id=f.id,
                project_id=f.project_id,
                relative_path=f.relative_path,
                language=f.language,
                size_bytes=f.size_bytes,
                line_count=f.line_count,
                ast_status=f.ast_status,
                file_hash=f.file_hash,
                created_at=f.created_at,
            )
            for f in files
        ],
        total=len(files),
    )


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Delete a project and cascade all associated files, symbols, and chunks.
    """
    project_repo = ProjectRepository(db)
    deleted = await project_repo.delete(project_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID '{project_id}' not found.",
        )
