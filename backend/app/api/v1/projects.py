"""
RepoMind AI — Projects & Repository Management API

Handles repository registration, file inspection, incremental scanning,
and project lifecycle management.
"""
import asyncio
import re
import time
import uuid
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile, status
from pathlib import Path, PurePosixPath
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.db.session import AsyncSessionLocal, get_db
from app.ingestion.service import IngestionService, RepositoryValidationError, validate_github_url, validate_repository_path
from app.core.config import get_settings
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


async def _index_project_in_background(project_id: str, github_url: str | None = None) -> None:
    """Run cloning, parsing, chunking, and embedding after the HTTP response."""
    async with AsyncSessionLocal() as session:
        project_repo = ProjectRepository(session)
        try:
            project = await project_repo.get_by_id(project_id)
            if not project:
                return
            started = time.time()
            base_metadata = dict(project.metadata_ or {})

            async def set_progress(phase: str, done: int = 0, total: int = 0) -> None:
                # A rollback inside indexing expires the row; reload before assigning.
                await session.refresh(project)
                project.metadata_ = {
                    **base_metadata,
                    "indexing": {
                        "phase": phase,
                        "files_done": done,
                        "files_total": total,
                        "started_at": started,
                        "updated_at": time.time(),
                    },
                }
                await session.commit()

            service = IngestionService(session)
            if github_url:
                await set_progress("cloning")
                project.path = str(await asyncio.to_thread(service.clone_github_repository, github_url))
            await set_progress("scanning")
            await service.sync_files(project)
            # Commit the scan before generating embeddings.  The UI can now
            # show the real file count while the slower vector work continues.
            await session.commit()
            from app.ingestion.symbol_extractor import SymbolExtractor

            async def embedding_progress(done: int, total: int) -> None:
                await set_progress("embedding", done, total)

            await SymbolExtractor(session).extract_symbols_for_project(project_id, on_progress=embedding_progress, only_pending=True)
            await session.refresh(project)
            project.metadata_ = {
                **base_metadata,
                "indexing": {"phase": "done", "duration_s": round(time.time() - started, 1)},
            }
            await project_repo.update_status(project_id, "indexed")
            await session.commit()
        except Exception as exc:
            await session.rollback()
            logger.error("background_indexing_failed", project_id=project_id, error=str(exc))
            async with AsyncSessionLocal() as error_session:
                await ProjectRepository(error_session).update_status(project_id, "error")
                await error_session.commit()


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    payload: ProjectCreateRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> ProjectResponse:
    """
    Import and register a local software repository.
    Validates path, runs initial file scanner, and persists file documents.
    """
    try:
        source = payload.path.strip()
        is_github = source.startswith(("http://", "https://"))
        if is_github:
            owner, repository = validate_github_url(source)
            project_path = str(Path(get_settings().workspace_root) / "github" / f"{owner}--{repository}")
        else:
            project_path = str(validate_repository_path(source))

        project_repo = ProjectRepository(db)
        project = await project_repo.get_by_path(project_path)
        if project is None:
            project = await project_repo.create(
                name=payload.name.strip() if payload.name and payload.name.strip() else project_path.rsplit("/", 1)[-1],
                path=project_path,
                settings=payload.settings,
                metadata={"root": project_path},
            )
        await project_repo.update_status(project.id, "indexing")
        background_tasks.add_task(_index_project_in_background, project.id, source if is_github else None)
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

    return ProjectResponse(
        id=project.id,
        name=project.name,
        path=project.path,
        status=project.status,
        settings=project.settings,
        metadata=project.metadata_,
        file_count=0,
        total_size_bytes=0,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


MAX_UPLOAD_FILES = 5000
MAX_UPLOAD_BYTES = 200 * 1024 * 1024
_UPLOAD_SKIP_PARTS = {".git", "node_modules", "venv", ".venv", "__pycache__", "dist", "build", ".next", ".idea", ".vscode"}


def _safe_upload_path(relative_name: str) -> PurePosixPath | None:
    """Return a safe relative path for an uploaded file, or None to skip it."""
    candidate = PurePosixPath(relative_name.replace("\\", "/"))
    if candidate.is_absolute() or ".." in candidate.parts or not candidate.parts:
        return None
    if any(part in _UPLOAD_SKIP_PARTS for part in candidate.parts[:-1]):
        return None
    return candidate


@router.post("/upload", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def upload_project(
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...),
    name: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
) -> ProjectResponse:
    """
    Import a folder chosen in the browser.

    The client sends every file with its folder-relative path as the filename.
    Files are copied into the managed workspace and then indexed exactly like a
    GitHub or path import, so the assistant stays read-only on the user's disk.
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files were uploaded.")
    if len(files) > MAX_UPLOAD_FILES:
        raise HTTPException(status_code=413, detail=f"Too many files (limit {MAX_UPLOAD_FILES}). Remove build output and dependencies, then retry.")

    first = _safe_upload_path(files[0].filename or "")
    root_hint = first.parts[0] if first and len(first.parts) > 1 else "upload"
    display_name = (name or "").strip() or root_hint
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", display_name).strip("-") or "upload"
    target = Path(get_settings().workspace_root).resolve() / "uploads" / f"{slug}-{uuid.uuid4().hex[:8]}"
    max_file = get_settings().max_file_size_mb * 1024 * 1024

    written = 0
    total_bytes = 0
    for upload in files:
        relative = _safe_upload_path(upload.filename or "")
        if relative is None:
            continue
        # Drop the chosen folder's own name so paths are repository-relative.
        parts = relative.parts[1:] if len(relative.parts) > 1 and relative.parts[0] == root_hint else relative.parts
        if not parts:
            continue
        data = await upload.read()
        if len(data) > max_file:
            continue
        total_bytes += len(data)
        if total_bytes > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="Upload exceeds 200 MB. Remove large assets and retry.")
        destination = target.joinpath(*parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        written += 1

    if written == 0:
        raise HTTPException(status_code=400, detail="No indexable files were found in the selected folder.")

    project_repo = ProjectRepository(db)
    project = await project_repo.create(
        name=display_name,
        path=str(target),
        settings={},
        metadata={"root": str(target), "source": "upload", "uploaded_files": written},
    )
    await project_repo.update_status(project.id, "indexing")
    await db.commit()
    background_tasks.add_task(_index_project_in_background, project.id, None)
    return ProjectResponse(
        id=project.id,
        name=project.name,
        path=project.path,
        status="indexing",
        settings=project.settings,
        metadata=project.metadata_,
        file_count=0,
        total_size_bytes=0,
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
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> ProjectScanResponse:
    """
    Trigger an incremental file scan on an existing repository.
    Returns immediately; the actual re-indexing runs in the background.
    """
    project_repo = ProjectRepository(db)
    proj = await project_repo.get_by_id(project_id)
    if not proj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID '{project_id}' not found.",
        )

    # Do the fast file-metadata scan synchronously so we can return a summary
    service = IngestionService(db)
    try:
        summary = await service.sync_files(proj)
        await project_repo.update_status(project_id, "indexing")
        await db.commit()
    except Exception as exc:
        await project_repo.update_status(project_id, "error")
        await db.commit()
        logger.error("scan_project_failed", project_id=project_id, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Incremental scan failed: {exc}",
        )

    # Symbol extraction + embedding runs in background (can take minutes)
    background_tasks.add_task(_index_project_in_background, project_id, None)

    return ProjectScanResponse(
        project_id=proj.id,
        status="indexing",
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
