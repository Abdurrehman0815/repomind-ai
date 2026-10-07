"""
RepoMind AI — Ingestion Package
"""
from app.ingestion.scanner import (
    scan_repository,
    detect_language,
    compute_file_hash,
    count_lines_and_size,
    ScannedFileInfo,
    LANGUAGE_MAP,
)
from app.ingestion.service import (
    IngestionService,
    IngestionSummary,
    validate_repository_path,
    RepositoryValidationError,
)

__all__ = [
    "scan_repository",
    "detect_language",
    "compute_file_hash",
    "count_lines_and_size",
    "ScannedFileInfo",
    "LANGUAGE_MAP",
    "IngestionService",
    "IngestionSummary",
    "validate_repository_path",
    "RepositoryValidationError",
]
