"""
RepoMind AI — Repository Ingestion Service

Coordinates scanning, path verification, incremental change detection,
and database persistence for projects and source file documents.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.ingestion.scanner import scan_repository, ScannedFileInfo
from app.models.project import Project
from app.models.file_document import FileDocument
from app.repositories.project_repository import ProjectRepository
from app.repositories.file_repository import FileRepository

logger = structlog.get_logger(__name__)

# Dangerous system paths disallowed from being imported as repositories
DISALLOWED_ROOTS = {
    "",
    "/",
    "/etc",
    "/root",
    "/var",
    "/bin",
    "/usr",
    "c:",
    "c:\\",
    "c:\\windows",
    "c:\\program files",
    "c:\\program files (x86)",
}


class RepositoryValidationError(Exception):
    """Raised when repository path or parameters are invalid or dangerous."""


class IngestionSummary:
    """Summary metrics of an ingestion or re-scan operation."""

    def __init__(self, project_id: str) -> None:
        self.project_id = project_id
        self.total_scanned: int = 0
        self.added_files: int = 0
        self.modified_files: int = 0
        self.unchanged_files: int = 0
        self.deleted_files: int = 0
        self.languages: dict[str, int] = {}
        self.total_size_bytes: int = 0
        self.total_lines: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "total_scanned": self.total_scanned,
            "added_files": self.added_files,
            "modified_files": self.modified_files,
            "unchanged_files": self.unchanged_files,
            "deleted_files": self.deleted_files,
            "languages": self.languages,
            "total_size_bytes": self.total_size_bytes,
            "total_lines": self.total_lines,
        }


def validate_repository_path(path_str: str) -> Path:
    """
    Validate that repository path exists, is a directory, and is not a forbidden system path.
    """
    if not path_str or not path_str.strip():
        raise RepositoryValidationError("Repository path cannot be empty.")

    try:
        resolved = Path(path_str.strip()).resolve()
    except Exception as exc:
        raise RepositoryValidationError(f"Invalid path format: {exc}")

    # Check against disallowed root paths
    normalized = str(resolved).lower().rstrip("\\/")
    if normalized in DISALLOWED_ROOTS or resolved.parent == resolved:
        raise RepositoryValidationError(f"Access denied: system root '{resolved}' cannot be indexed.")

    if not resolved.exists():
        raise RepositoryValidationError(f"Directory does not exist: {resolved}")
    if not resolved.is_dir():
        raise RepositoryValidationError(f"Path is not a directory: {resolved}")

    return resolved


class IngestionService:
    """Service handling repository import and incremental document updates."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.project_repo = ProjectRepository(session)
        self.file_repo = FileRepository(session)
        self.settings = get_settings()

    def _get_repository_commit(self, project_path: str) -> Optional[str]:
        """
        Get the current git commit hash for the repository at project_path.
        Returns None if not a git repository or on error.
        """
        try:
            # Run git rev-parse HEAD in the project directory
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                commit_hash = result.stdout.strip()
                # Validate that it looks like a hash (40 hex characters)
                if len(commit_hash) == 40 and all(c in "0123456789abcdefABCDEF" for c in commit_hash):
                    return commit_hash
                else:
                    logger.warning("unexpected_git_output", output=commit_hash)
                    return None
            else:
                logger.warning("git_command_failed", stderr=result.stderr)
                return None
        except subprocess.TimeoutExpired:
            logger.warning("git_command_timeout")
            return None
        except Exception as e:
            logger.error("error_getting_repository_commit", error=str(e))
            return None

    async def import_repository(
        self,
        path: str,
        name: str | None = None,
        settings: dict[str, Any] | None = None,
    ) -> tuple[Project, IngestionSummary]:
        """
        Validate path, register/find project, and perform initial file scan.
        """
        validated_path = validate_repository_path(path)
        canonical_path_str = str(validated_path)
        project_name = name.strip() if name and name.strip() else validated_path.name

        # Check if project already exists for this path
        existing_project = await self.project_repo.get_by_path(canonical_path_str)
        if existing_project:
            project = existing_project
        else:
            project = await self.project_repo.create(
                name=project_name,
                path=canonical_path_str,
                settings=settings or {},
                metadata={"root": canonical_path_str},
            )

        # Mark status as indexing
        await self.project_repo.update_status(project.id, "indexing")

        try:
            summary = await self.sync_files(project)
            # Update status to unindexed (files imported, chunks/symbols pending in Phase 4)
            await self.project_repo.update_status(project.id, "unindexed")

            # Update repository commit hash
            commit_hash = self._get_repository_commit(canonical_path_str)
            if commit_hash:
                await self.project_repo.update_commit_hash(project.id, commit_hash)
                logger.info("repository_commit_updated", project_id=project.id, commit_hash=commit_hash[:8])
            else:
                logger.warning("failed_to_get_repository_commit", project_id=project.id)

            return project, summary
        except Exception as exc:
            logger.error("import_repository_failed", project_id=project.id, error=str(exc))
            await self.project_repo.update_status(project.id, "error")
            raise

    async def sync_files(self, project: Project) -> IngestionSummary:
        """
        Scan repository files and incrementally update database records.
        """
        summary = IngestionSummary(project.id)
        max_size = self.settings.max_file_size_bytes

        # Retrieve current files in database
        existing_files = await self.file_repo.list_by_project(project.id)
        existing_by_rel: dict[str, FileDocument] = {
            doc.relative_path: doc for doc in existing_files
        }
        seen_rel_paths: set[str] = set()

        for scanned in scan_repository(project.path, max_file_size_bytes=max_size):
            summary.total_scanned += 1
            summary.total_size_bytes += scanned.size_bytes
            summary.total_lines += scanned.line_count
            summary.languages[scanned.language] = summary.languages.get(scanned.language, 0) + 1
            seen_rel_paths.add(scanned.relative_path)

            existing_doc = existing_by_rel.get(scanned.relative_path)

            if existing_doc is None:
                # New file
                await self.file_repo.create(
                    project_id=project.id,
                    path=scanned.absolute_path,
                    relative_path=scanned.relative_path,
                    file_hash=scanned.file_hash,
                    language=scanned.language,
                    size_bytes=scanned.size_bytes,
                    line_count=scanned.line_count,
                    ast_status="pending",
                )
                summary.added_files += 1
            elif existing_doc.file_hash != scanned.file_hash:
                # Modified file
                existing_doc.file_hash = scanned.file_hash
                existing_doc.size_bytes = scanned.size_bytes
                existing_doc.line_count = scanned.line_count
                existing_doc.language = scanned.language
                existing_doc.ast_status = "pending"
                summary.modified_files += 1
            else:
                # Unchanged file
                summary.unchanged_files += 1

        # Check for deleted files
        for rel_path, doc in existing_by_rel.items():
            if rel_path not in seen_rel_paths:
                await self.session.delete(doc)
                summary.deleted_files += 1

        await self.session.flush()
        return summary