"""
RepoMind AI — Parser Interface and Data Structures
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ExtractedSymbol:
    """Represents a code symbol extracted from an AST."""
    name: str
    kind: str  # function | class | method | interface | type | enum | variable
    line_start: int
    line_end: int
    signature: str | None = None
    docstring: str | None = None
    parent_name: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExtractedDependency:
    """Represents an imported module or symbol."""
    module: str
    raw_statement: str
    line_number: int
    symbol_name: str | None = None


@dataclass
class ParseResult:
    """Output of parsing a source code file."""
    symbols: list[ExtractedSymbol] = field(default_factory=list)
    dependencies: list[ExtractedDependency] = field(default_factory=list)
    status: str = "parsed"  # parsed | partial | error | skipped
    error_message: str | None = None


class BaseCodeParser(ABC):
    """Abstract base class for language AST parsers."""

    @abstractmethod
    def can_parse(self, language: str) -> bool:
        """Check if parser supports the given language."""
        pass

    @abstractmethod
    def parse(self, code: str, file_path: str = "") -> ParseResult:
        """Parse source code into symbols and dependencies."""
        pass
