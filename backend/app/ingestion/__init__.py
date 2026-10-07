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
from app.ingestion.parsers import (
    BaseCodeParser,
    ExtractedSymbol,
    ExtractedDependency,
    ParseResult,
    get_parser_for_language,
    parse_file_content,
)
from app.ingestion.symbol_extractor import (
    SymbolExtractor,
    SymbolExtractionStats,
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
    "BaseCodeParser",
    "ExtractedSymbol",
    "ExtractedDependency",
    "ParseResult",
    "get_parser_for_language",
    "parse_file_content",
    "SymbolExtractor",
    "SymbolExtractionStats",
]
