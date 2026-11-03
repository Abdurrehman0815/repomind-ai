"""
RepoMind AI — Code Chunking Service

Implements logical chunking strategy for source code files:
Priority: function > class > method > module section > fallback line-based chunk
Each chunk includes metadata for retrieval and citation purposes.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, List, Optional, Tuple
import structlog
import tiktoken

from app.models.code_symbol import CodeSymbol
from app.models.file_document import FileDocument
from app.ai.providers.embedding_registry import get_embedding_provider
from app.ai.providers.embedding_base import EmbeddingOptions
from app.ingestion.text_io import read_source_text

logger = structlog.get_logger(__name__)


@dataclass
class CodeChunkData:
    """Temporary chunk data before persistence."""
    content: str
    start_line: int
    end_line: int
    chunk_type: str  # function | class | method | module_section | line_based
    symbol_name: Optional[str] = None
    parent_symbol_id: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)


class Chunker:
    """Implements logical chunking strategy for source code."""

    def __init__(
        self,
        max_tokens_per_chunk: int = 512,
        overlap_lines: int = 20,
        encoding_name: str = "cl100k_base"
    ):
        """
        Initialize the chunker.

        Args:
            max_tokens_per_chunk: Maximum tokens per chunk (default 512 for embedding models)
            overlap_lines: Number of lines to overlap between chunks for context preservation
            encoding_name: Tokenizer encoding to use for token counting
        """
        self.max_tokens_per_chunk = max_tokens_per_chunk
        self.overlap_lines = overlap_lines
        self.encoding = tiktoken.get_encoding(encoding_name)
        self.logger = logger

    def count_tokens(self, text: str) -> int:
        """Count tokens in text using the configured encoder."""
        return len(self.encoding.encode(text))

    def chunk_file(
        self,
        file_doc: FileDocument,
        symbols: List[CodeSymbol],
        content: Optional[str] = None
    ) -> List[CodeChunkData]:
        """
        Chunk a source file based on symbols and fallback strategies.

        Args:
            file_doc: File document metadata
            symbols: List of extracted symbols from the file
            content: Optional file content (will be read if not provided)

        Returns:
            List of CodeChunkData objects ready for persistence
        """
        if content is None:
            try:
                content = read_source_text(file_doc.path)
            except Exception as exc:
                self.logger.warning(
                    "failed_to_read_file_for_chunking",
                    path=file_doc.path,
                    error=str(exc)
                )
                return []

        lines = content.splitlines()
        chunks: List[CodeChunkData] = []

        # Group symbols by type for priority-based processing
        functions = [s for s in symbols if s.kind == "function"]
        classes = [s for s in symbols if s.kind == "class"]
        methods = [s for s in symbols if s.kind == "method"]

        # Process in priority order: functions, classes, methods, then module sections
        processed_ranges: set[Tuple[int, int]] = set()

        # 1. Process functions (highest priority)
        for symbol in functions:
            chunk_data = self._create_symbol_chunk(
                symbol, lines, content, "function"
            )
            # Handle case where _create_symbol_chunk might return a list (from splitting)
            if chunk_data:
                if isinstance(chunk_data, list):
                    # Handle multiple chunks from splitting
                    for chunk in chunk_data:
                        if chunk and self._is_valid_chunk(chunk, processed_ranges):
                            chunks.append(chunk)
                            processed_ranges.add((chunk.start_line, chunk.end_line))
                else:
                    # Handle single chunk
                    if self._is_valid_chunk(chunk_data, processed_ranges):
                        chunks.append(chunk_data)
                        processed_ranges.add((chunk_data.start_line, chunk_data.end_line))

        # 2. Process classes
        for symbol in classes:
            chunk_data = self._create_symbol_chunk(
                symbol, lines, content, "class"
            )
            # Handle case where _create_symbol_chunk might return a list (from splitting)
            if chunk_data:
                if isinstance(chunk_data, list):
                    # Handle multiple chunks from splitting
                    for chunk in chunk_data:
                        if chunk and self._is_valid_chunk(chunk, processed_ranges):
                            chunks.append(chunk)
                            processed_ranges.add((chunk.start_line, chunk.end_line))
                else:
                    # Handle single chunk
                    if self._is_valid_chunk(chunk_data, processed_ranges):
                        chunks.append(chunk_data)
                        processed_ranges.add((chunk_data.start_line, chunk_data.end_line))

        # 3. Process methods
        for symbol in methods:
            chunk_data = self._create_symbol_chunk(
                symbol, lines, content, "method"
            )
            # Handle case where _create_symbol_chunk might return a list (from splitting)
            if chunk_data:
                if isinstance(chunk_data, list):
                    # Handle multiple chunks from splitting
                    for chunk in chunk_data:
                        if chunk and self._is_valid_chunk(chunk, processed_ranges):
                            chunks.append(chunk)
                            processed_ranges.add((chunk.start_line, chunk.end_line))
                else:
                    # Handle single chunk
                    if self._is_valid_chunk(chunk_data, processed_ranges):
                        chunks.append(chunk_data)
                        processed_ranges.add((chunk_data.start_line, chunk_data.end_line))

        # 4. Process module sections (remaining code not covered by symbols)
        module_chunks = self._create_module_section_chunks(
            lines, content, processed_ranges
        )
        chunks.extend(module_chunks)

        # 5. Fallback: line-based chunking for any remaining uncovered areas
        # This ensures we don't miss any content
        if not chunks or self._has_uncovered_content(lines, processed_ranges):
            fallback_chunks = self._create_line_based_chunks(
                lines, content, processed_ranges
            )
            chunks.extend(fallback_chunks)

        # Sort chunks by start line for consistent ordering
        chunks.sort(key=lambda c: c.start_line)

        # Assign sequential chunk indices
        for i, chunk in enumerate(chunks):
            chunk.metadata["chunk_index"] = i

        return chunks

    def _create_symbol_chunk(
        self,
        symbol: CodeSymbol,
        lines: List[str],
        content: str,
        chunk_type: str
    ) -> Optional[CodeChunkData]:
        """Create a chunk from a symbol definition."""
        try:
            start_line = max(1, symbol.line_start)  # Ensure 1-indexed
            end_line = max(start_line, symbol.line_end)

            # Validate line ranges
            if start_line < 1 or end_line > len(lines) or start_line > end_line:
                self.logger.warning(
                    "invalid_symbol_line_range",
                    symbol=symbol.name,
                    start=start_line,
                    end=end_line,
                    file_lines=len(lines)
                )
                return None

            # Extract content for this symbol
            symbol_lines = lines[start_line-1:end_line]  # Convert to 0-indexed slicing
            symbol_content = "\n".join(symbol_lines)

            # Check if chunk is too large and needs splitting
            if self.count_tokens(symbol_content) > self.max_tokens_per_chunk:
                split_chunks = self._split_oversized_chunk(
                    symbol, lines, content, chunk_type, start_line, end_line
                )
                # Return all split chunks - the calling code handles lists
                return split_chunks if split_chunks else None

            # Prepare metadata
            metadata = {
                "symbol_name": symbol.name,
                "symbol_kind": symbol.kind,
                "chunk_type": chunk_type,
                "has_docstring": bool(symbol.docstring),
            }
            if symbol.signature:
                metadata["symbol_signature"] = symbol.signature
            if symbol.parent_symbol_id:
                metadata["parent_symbol_id"] = symbol.parent_symbol_id

            # SQLAlchemy declarative models inherit ``Base.metadata``. That is
            # a SQLAlchemy MetaData object, not per-symbol metadata, and cannot
            # be merged into this dictionary. Only merge metadata when a model
            # explicitly exposes a dictionary-valued attribute.
            symbol_metadata = getattr(symbol, "metadata", None)
            if isinstance(symbol_metadata, dict):
                metadata.update(symbol_metadata)

            return CodeChunkData(
                content=symbol_content,
                start_line=start_line,
                end_line=end_line,
                chunk_type=chunk_type,
                symbol_name=symbol.name,
                parent_symbol_id=symbol.parent_symbol_id,
                metadata=metadata
            )
        except Exception as exc:
            self.logger.warning(
                "failed_to_create_symbol_chunk",
                symbol=symbol.name,
                error=str(exc)
            )
            return None

    def _split_oversized_chunk(
        self,
        symbol: CodeSymbol,
        lines: List[str],
        content: str,
        chunk_type: str,
        start_line: int,
        end_line: int
    ) -> List[CodeChunkData]:
        """
        Split an oversized symbol chunk into smaller pieces.
        Attempts to split at logical boundaries (empty lines, etc.).
        Returns a list of chunks.
        """
        chunks = []
        symbol_lines = lines[start_line-1:end_line]
        symbol_content = "\n".join(symbol_lines)

        # Try to split by empty lines first
        sections = re.split(r'\n\s*\n', symbol_content)
        if len(sections) > 1:
            # Reconstruct sections with line numbers
            current_line = start_line
            for section in sections:
                if not section.strip():
                    # Count lines in empty section
                    empty_lines = section.count('\n') + 1
                    current_line += empty_lines
                    continue

                section_lines = section.splitlines()
                section_end_line = current_line + len(section_lines) - 1

                section_content = section
                if self.count_tokens(section_content) <= self.max_tokens_per_chunk:
                    metadata = {
                        "symbol_name": symbol.name,
                        "symbol_kind": symbol.kind,
                        "chunk_type": f"{chunk_type}_section",
                        "is_partial_symbol": True,
                    }
                    if symbol.signature:
                        metadata["symbol_signature"] = symbol.signature

                    chunks.append(CodeChunkData(
                        content=section_content,
                        start_line=current_line,
                        end_line=section_end_line,
                        chunk_type=f"{chunk_type}_section",
                        symbol_name=symbol.name,
                        parent_symbol_id=symbol.parent_symbol_id,
                        metadata=metadata
                    ))

                current_line = section_end_line + 2  # Skip the empty line(s)
        else:
            # Fallback: split lines to ensure each chunk is under token limit
            current_chunk_lines = []
            current_chunk_start = start_line
            part_number = 1

            for i, line in enumerate(symbol_lines):
                line_num = start_line + i
                line_content = line

                # Test if adding this line would exceed the limit
                test_content = "\n".join(current_chunk_lines + [line_content])
                if current_chunk_lines and self.count_tokens(test_content) > self.max_tokens_per_chunk:
                    # Current chunk is full, create it
                    chunk_content = "\n".join(current_chunk_lines)
                    chunk_end_line = current_chunk_start + len(current_chunk_lines) - 1

                    metadata = {
                        "symbol_name": symbol.name,
                        "symbol_kind": symbol.kind,
                        "chunk_type": f"{chunk_type}_part_{part_number}",
                        "is_partial_symbol": True,
                    }
                    if symbol.signature:
                        metadata["symbol_signature"] = symbol.signature

                    chunks.append(CodeChunkData(
                        content=chunk_content,
                        start_line=current_chunk_start,
                        end_line=chunk_end_line,
                        chunk_type=f"{chunk_type}_part_{part_number}",
                        symbol_name=symbol.name,
                        parent_symbol_id=symbol.parent_symbol_id,
                        metadata=metadata
                    ))

                    # Start new chunk with current line
                    current_chunk_lines = [line_content]
                    current_chunk_start = line_num
                    part_number += 1
                else:
                    # Add line to current chunk
                    current_chunk_lines.append(line_content)

            # Don't forget the last chunk
            if current_chunk_lines:
                chunk_content = "\n".join(current_chunk_lines)
                chunk_end_line = current_chunk_start + len(current_chunk_lines) - 1

                metadata = {
                    "symbol_name": symbol.name,
                    "symbol_kind": symbol.kind,
                    "chunk_type": f"{chunk_type}_part_{part_number}",
                    "is_partial_symbol": True,
                }
                if symbol.signature:
                    metadata["symbol_signature"] = symbol.signature

                chunks.append(CodeChunkData(
                    content=chunk_content,
                    start_line=current_chunk_start,
                    end_line=chunk_end_line,
                    chunk_type=f"{chunk_type}_part_{part_number}",
                    symbol_name=symbol.name,
                    parent_symbol_id=symbol.parent_symbol_id,
                    metadata=metadata
                ))

        return chunks

    def _create_module_section_chunks(
        self,
        lines: List[str],
        content: str,
        processed_ranges: set[Tuple[int, int]]
    ) -> List[CodeChunkData]:
        """Create chunks for module-level code not covered by symbols."""
        chunks = []

        # Find gaps between processed symbol ranges
        sorted_ranges = sorted(processed_ranges)
        prev_end = 0

        for start, end in sorted_ranges:
            # Check for gap before this symbol
            if start > prev_end + 1:
                gap_start = prev_end + 1
                gap_end = start - 1

                gap_lines = lines[gap_start-1:gap_end]  # Convert to 0-indexed
                gap_content = "\n".join(gap_lines)

                if gap_content.strip():  # Only create chunk if there's actual content
                    if self.count_tokens(gap_content) <= self.max_tokens_per_chunk:
                        chunks.append(CodeChunkData(
                            content=gap_content,
                            start_line=gap_start,
                            end_line=gap_end,
                            chunk_type="module_section",
                            metadata={
                                "chunk_type": "module_section",
                                "is_module_level": True
                            }
                        ))
                    else:
                        # Split large module sections
                        chunks.extend(self._split_large_content(
                            gap_content, gap_start, gap_end, "module_section"
                        ))

            prev_end = max(prev_end, end)

        # Check for gap after last symbol
        if prev_end < len(lines):
            gap_start = prev_end + 1
            gap_end = len(lines)

            gap_lines = lines[gap_start-1:gap_end]
            gap_content = "\n".join(gap_lines)

            if gap_content.strip():
                if self.count_tokens(gap_content) <= self.max_tokens_per_chunk:
                    chunks.append(CodeChunkData(
                        content=gap_content,
                        start_line=gap_start,
                        end_line=gap_end,
                        chunk_type="module_section",
                        metadata={
                            "chunk_type": "module_section",
                            "is_module_level": True
                        }
                    ))
                else:
                    chunks.extend(self._split_large_content(
                        gap_content, gap_start, gap_end, "module_section"
                    ))

        return chunks

    def _create_line_based_chunks(
        self,
        lines: List[str],
        content: str,
        processed_ranges: set[Tuple[int, int]]
    ) -> List[CodeChunkData]:
        """Create fallback line-based chunks for any uncovered content."""
        chunks = []

        # Find all uncovered line ranges
        covered = [False] * (len(lines) + 1)  # 1-indexed, ignore index 0
        for start, end in processed_ranges:
            for line_num in range(start, min(end + 1, len(covered))):
                covered[line_num] = True

        # Find contiguous uncovered segments
        i = 1
        while i <= len(lines):
            if not covered[i]:
                # Start of uncovered segment
                segment_start = i
                while i <= len(lines) and not covered[i]:
                    i += 1
                segment_end = i - 1

                # Create chunk for this segment
                segment_lines = lines[segment_start-1:segment_end]
                segment_content = "\n".join(segment_lines)

                if segment_content.strip():
                    if self.count_tokens(segment_content) <= self.max_tokens_per_chunk:
                        chunks.append(CodeChunkData(
                            content=segment_content,
                            start_line=segment_start,
                            end_line=segment_end,
                            chunk_type="line_based",
                            metadata={
                                "chunk_type": "line_based",
                                "is_fallback": True
                            }
                        ))
                    else:
                        chunks.extend(self._split_large_content(
                            segment_content, segment_start, segment_end, "line_based"
                        ))
            else:
                i += 1

        return chunks

    def _split_large_content(
        self,
        content: str,
        start_line: int,
        end_line: int,
        chunk_type: str
    ) -> List[CodeChunkData]:
        """Split large content into token-appropriate chunks."""
        chunks = []
        lines = content.splitlines()

        if not lines:
            return chunks

        current_chunk_lines = []
        current_chunk_start = start_line
        current_token_count = 0

        for i, line in enumerate(lines):
            line_num = start_line + i
            line_tokens = self.count_tokens(line + "\n")  # Include newline

            if current_token_count + line_tokens > self.max_tokens_per_chunk and current_chunk_lines:
                # Finalize current chunk
                chunk_content = "\n".join(current_chunk_lines)
                chunk_end_line = current_chunk_start + len(current_chunk_lines) - 1

                chunks.append(CodeChunkData(
                    content=chunk_content,
                    start_line=current_chunk_start,
                    end_line=chunk_end_line,
                    chunk_type=f"{chunk_type}_split",
                    metadata={
                        "chunk_type": f"{chunk_type}_split",
                        "is_split": True
                    }
                ))

                # Start new chunk with overlap
                overlap_start = max(0, len(current_chunk_lines) - self.overlap_lines)
                current_chunk_lines = current_chunk_lines[overlap_start:]
                current_chunk_start = line_num - len(current_chunk_lines)
                current_token_count = self.count_tokens("\n".join(current_chunk_lines))

            current_chunk_lines.append(line)
            current_token_count += line_tokens

        # Add final chunk if there's content
        if current_chunk_lines:
            chunk_content = "\n".join(current_chunk_lines)
            chunk_end_line = current_chunk_start + len(current_chunk_lines) - 1

            chunks.append(CodeChunkData(
                content=chunk_content,
                start_line=current_chunk_start,
                end_line=chunk_end_line,
                chunk_type=f"{chunk_type}_split",
                metadata={
                    "chunk_type": f"{chunk_type}_split",
                    "is_split": True
                }
            ))

        return chunks

    def _is_valid_chunk(
        self,
        chunk: CodeChunkData,
        processed_ranges: set[Tuple[int, int]]
    ) -> bool:
        """Validate that a chunk is valid and doesn't duplicate existing ranges."""
        # Check line bounds
        if chunk.start_line < 1 or chunk.end_line < chunk.start_line:
            return False

        # Check for overlap with already processed ranges (allow small overlaps for context)
        for start, end in processed_ranges:
            # Allow overlap of up to overlap_lines for context preservation
            if not (chunk.end_line < start - self.overlap_lines or
                   chunk.start_line > end + self.overlap_lines):
                # Significant overlap - check if it's mostly duplicate
                overlap_start = max(chunk.start_line, start)
                overlap_end = min(chunk.end_line, end)
                if overlap_end >= overlap_start:
                    overlap_size = overlap_end - overlap_start + 1
                    chunk_size = chunk.end_line - chunk.start_line + 1
                    if overlap_size > chunk_size * 0.5:  # More than 50% overlap
                        return False

        return True

    def _has_uncovered_content(
        self,
        lines: List[str],
        processed_ranges: set[Tuple[int, int]]
    ) -> bool:
        """Check if there's any uncovered content that needs fallback chunking."""
        if not lines:
            return False

        covered = [False] * (len(lines) + 1)  # 1-indexed
        for start, end in processed_ranges:
            for line_num in range(start, min(end + 1, len(covered))):
                covered[line_num] = True

        return any(not covered[i] for i in range(1, len(lines) + 1))

    async def create_chunks_for_file(
        self,
        file_doc: FileDocument,
        symbols: List[CodeSymbol],
        chunk_repo: Any,  # ChunkRepository
        session: Any  # AsyncSession
    ) -> List[Any]:  # List of CodeChunk
        """
        Create and persist chunks for a file.

        Args:
            file_doc: File document to chunk
            symbols: Extracted symbols from the file
            chunk_repo: Chunk repository for persistence
            session: Database session

        Returns:
            List of persisted CodeChunk objects
        """
        # Generate chunk data
        chunk_data_list = self.chunk_file(file_doc, symbols)

        if not chunk_data_list:
            return []

        # Generate embeddings for all chunks
        texts = [chunk_data.content for chunk_data in chunk_data_list]
        embedding_provider = get_embedding_provider()

        try:
            embedding_response = await embedding_provider.embed(
                texts,
                EmbeddingOptions(batch_size=32, normalize=True)
            )
            embeddings = embedding_response.embeddings

            # Verify we got embeddings for all chunks
            if len(embeddings) != len(chunk_data_list):
                self.logger.warning(
                    "Embedding count mismatch",
                    expected=len(chunk_data_list),
                    received=len(embeddings)
                )
                # If we don't have embeddings for all, proceed without them
                embeddings = [None] * len(chunk_data_list)
        except Exception as e:
            self.logger.error(
                "Failed to generate embeddings for chunks",
                error=str(e),
                chunk_count=len(chunk_data_list)
            )
            # Proceed without embeddings if generation fails
            embeddings = [None] * len(chunk_data_list)

        # Persist chunks with embeddings
        persisted_chunks = []
        # Capture ids once: a failed flush expires the ORM row, and reading it
        # afterwards would raise instead of logging.
        project_id, file_id = file_doc.project_id, file_doc.id
        for i, (chunk_data, embedding) in enumerate(zip(chunk_data_list, embeddings)):
            try:
                chunk = await chunk_repo.create(
                    project_id=project_id,
                    file_id=file_id,
                    chunk_index=i,
                    content=chunk_data.content,
                    start_line=chunk_data.start_line,
                    end_line=chunk_data.end_line,
                    token_count=self.count_tokens(chunk_data.content),
                    embedding=embedding,
                    metadata=chunk_data.metadata
                )
                persisted_chunks.append(chunk)

                self.logger.debug(
                    "created_code_chunk",
                    chunk_id=chunk.id,
                    file_id=file_id,
                    lines=f"{chunk.start_line}-{chunk.end_line}",
                    type=chunk_data.chunk_type,
                    has_embedding=embedding is not None
                )
            except Exception as exc:
                self.logger.error(
                    "failed_to_persist_chunk",
                    file_id=file_id,
                    chunk_index=i,
                    error=str(exc)
                )
                # A failed flush poisons the session; let the caller roll back this file.
                raise

        return persisted_chunks