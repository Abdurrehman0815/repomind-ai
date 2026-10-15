"""
RepoMind AI — Citation Service
"""
from __future__ import annotations

import hashlib
import os
from typing import Optional
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.file_document import FileDocument
from app.models.project import Project
from app.models.code_chunk import CodeChunk
from app.schemas.citation import CitationResponse

logger = structlog.get_logger(__name__)


class CitationService:
    """Service for validating and formatting citations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_citation_from_chunk(
        self,
        chunk: CodeChunk,
        project_id: str
    ) -> CitationResponse:
        """
        Create a citation from a code chunk.

        Args:
            chunk: The code chunk to create citation from
            project_id: ID of the project

        Returns:
            CitationResponse with validation and metadata
        """
        # Get the file document for this chunk
        file_doc = await self.session.get(FileDocument, chunk.file_id)
        if not file_doc:
            logger.warning("file_document_not_found", file_id=chunk.file_id)
            # Return a basic citation with unknown status
            return CitationResponse(
                file_path="unknown",
                start_line=chunk.start_line,
                end_line=chunk.end_line,
                symbol=self._extract_symbol_from_chunk(chunk),
                file_hash="unknown",
                repository_commit=None,
                is_stale=True,  # Mark as stale since we can't validate
                repository_id=project_id
            )

        # Get the project to get repository commit and path
        project = await self.session.get(Project, project_id)
        if not project:
            logger.warning("project_not_found", project_id=project_id)
            return CitationResponse(
                file_path=file_doc.relative_path,
                start_line=chunk.start_line,
                end_line=chunk.end_line,
                symbol=self._extract_symbol_from_chunk(chunk),
                file_hash=file_doc.file_hash,
                repository_commit=None,
                is_stale=True,
                repository_id=project_id
            )

        # Extract symbol from chunk metadata or try to get from associated symbol
        symbol = self._extract_symbol_from_chunk(chunk)

        # Check if the file is stale by comparing stored hash with current file hash
        is_stale = await self._is_file_stale(project.path, file_doc.relative_path, file_doc.file_hash)

        # Get repository commit from project (we'll store this in Project model)
        repository_commit = getattr(project, 'repository_commit', None)

        return CitationResponse(
            file_path=file_doc.relative_path,
            start_line=chunk.start_line,
            end_line=chunk.end_line,
            symbol=symbol,
            file_hash=file_doc.file_hash,
            repository_commit=repository_commit,
            is_stale=is_stale,
            repository_id=project_id
        )

    def _extract_symbol_from_chunk(self, chunk: CodeChunk) -> Optional[str]:
        """
        Extract symbol name from chunk metadata.
        The metadata may contain symbol information from the ingestion process.
        """
        metadata = chunk.metadata_
        if isinstance(metadata, dict):
            # Try to get symbol name from metadata
            # This depends on how metadata is populated during ingestion
            symbol_name = metadata.get('symbol_name')
            if symbol_name:
                return symbol_name
            # Try other possible keys
            for key in ['symbol', 'name', 'function_name', 'class_name']:
                if key in metadata and isinstance(metadata[key], str):
                    return metadata[key]
        return None

    async def _is_file_stale(self, project_path: str, relative_path: str, stored_hash: str) -> bool:
        """
        Check if a file has changed by comparing stored hash with current file hash.

        Args:
            project_path: Absolute path to the project repository
            relative_path: Relative path of the file from project root
            stored_hash: The file hash stored in the database

        Returns:
            True if file is stale (hash doesn't match or file missing), False otherwise
        """
        try:
            file_path = os.path.join(project_path, relative_path)
            if not os.path.isfile(file_path):
                logger.warning("file_not_found", file_path=file_path)
                return True  # File missing is definitely stale

            # Compute current hash
            with open(file_path, 'rb') as f:
                content = f.read()
            current_hash = hashlib.sha256(content).hexdigest()

            # Compare hashes
            is_stale = current_hash != stored_hash
            if is_stale:
                logger.debug(
                    "file_stale_detected",
                    file_path=file_path,
                    stored_hash=stored_hash[:8],
                    current_hash=current_hash[:8]
                )
            return is_stale
        except Exception as e:
            logger.error("error_checking_file_staleness", error=str(e), file_path=relative_path)
            return True  # Assume stale on error to be safe

    async def validate_citation(self, citation: CitationResponse, project_path: str) -> Tuple[bool, str]:
        """
        Validate a citation against the current state of the repository.

        Args:
            citation: The citation to validate
            project_path: Absolute path to the project repository

        Returns:
            Tuple of (is_valid, reason_if_invalid)
        """
        # Check if the file exists
        file_path = os.path.join(project_path, citation.file_path)
        if not os.path.isfile(file_path):
            return False, f"File not found: {citation.file_path}"

        # Compute current hash and compare
        try:
            with open(file_path, 'rb') as f:
                content = f.read()
            current_hash = hashlib.sha256(content).hexdigest()
            if current_hash != citation.file_hash:
                return False, f"File hash mismatch: stored {citation.file_hash[:8]}, current {current_hash[:8]}"
        except Exception as e:
            return False, f"Error reading file: {str(e)}"

        # If we have a repository commit, we could check if it matches current HEAD, but we skip for simplicity
        return True, "Citation is valid"


# Initialize structlog if not already configured
if not structlog.get_config().get('processors'):
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=False,
    )