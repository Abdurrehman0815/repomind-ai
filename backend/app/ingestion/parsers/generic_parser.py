"""
RepoMind AI — Generic Multi-Language Code Parser

Structural parser supporting Go, Rust, Java, C, C++, C#, Kotlin, Swift, and SQL.
Extracts functions, methods, structs, classes, and interfaces with signature spans.
"""
from __future__ import annotations

import re
import structlog

from app.ingestion.parsers.base import (
    BaseCodeParser,
    ExtractedSymbol,
    ExtractedDependency,
    ParseResult,
)

logger = structlog.get_logger(__name__)

# Heuristic patterns for multi-language constructs
RE_GO_FUNC = re.compile(r"^func\s+(?:\((?:[^)]+)\)\s+)?([a-zA-Z0-9_]+)\s*\(")
RE_GO_TYPE = re.compile(r"^type\s+([a-zA-Z0-9_]+)\s+(?:struct|interface)")
RE_RUST_FN = re.compile(r"^(?:pub(?:\([^)]*\))?\s+)?(?:async\s+)?fn\s+([a-zA-Z0-9_]+)\s*(?:<[^>]*>)?\s*\(")
RE_RUST_STRUCT = re.compile(r"^(?:pub(?:\([^)]*\))?\s+)?(?:struct|enum|trait)\s+([a-zA-Z0-9_]+)")
RE_JAVA_CLASS = re.compile(r"^(?:(?:public|private|protected|abstract|static|final)\s+)*(?:class|interface|enum)\s+([a-zA-Z0-9_]+)")
RE_JAVA_METHOD = re.compile(r"^(?:(?:public|private|protected|static|final|synchronized|override)\s+)+[a-zA-Z0-9_<>\[\],\s]+\s+([a-zA-Z0-9_]+)\s*\(")
RE_SQL_CREATE = re.compile(r"^CREATE\s+(?:OR\s+REPLACE\s+)?(?:TABLE|VIEW|FUNCTION|PROCEDURE|TRIGGER)\s+(?:IF\s+NOT\s+EXISTS\s+)?([a-zA-Z0-9_.\"]+)", re.IGNORECASE)


class GenericMultiLanguageParser(BaseCodeParser):
    """Fallback parser for languages without specialized AST implementations."""

    def can_parse(self, language: str) -> bool:
        # Accepts any recognized text language
        return True

    def parse(self, code: str, file_path: str = "") -> ParseResult:
        if not code or not code.strip():
            return ParseResult(symbols=[], dependencies=[], status="parsed")

        symbols: list[ExtractedSymbol] = []
        dependencies: list[ExtractedDependency] = []
        lines = code.splitlines()

        for idx, line in enumerate(lines, start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("//") or stripped.startswith("#"):
                continue

            # Go functions and types
            go_func = RE_GO_FUNC.match(stripped)
            if go_func:
                symbols.append(
                    ExtractedSymbol(
                        name=go_func.group(1),
                        kind="function",
                        line_start=idx,
                        line_end=idx,
                        signature=stripped.rstrip("{").strip(),
                    )
                )
                continue

            go_type = RE_GO_TYPE.match(stripped)
            if go_type:
                symbols.append(
                    ExtractedSymbol(
                        name=go_type.group(1),
                        kind="class",
                        line_start=idx,
                        line_end=idx,
                        signature=stripped.rstrip("{").strip(),
                    )
                )
                continue

            # Rust functions and structs
            rust_fn = RE_RUST_FN.match(stripped)
            if rust_fn:
                symbols.append(
                    ExtractedSymbol(
                        name=rust_fn.group(1),
                        kind="function",
                        line_start=idx,
                        line_end=idx,
                        signature=stripped.rstrip("{").strip(),
                    )
                )
                continue

            rust_struct = RE_RUST_STRUCT.match(stripped)
            if rust_struct:
                symbols.append(
                    ExtractedSymbol(
                        name=rust_struct.group(1),
                        kind="class",
                        line_start=idx,
                        line_end=idx,
                        signature=stripped.rstrip("{").strip(),
                    )
                )
                continue

            # Java / C++ classes and methods
            java_class = RE_JAVA_CLASS.match(stripped)
            if java_class:
                symbols.append(
                    ExtractedSymbol(
                        name=java_class.group(1),
                        kind="class",
                        line_start=idx,
                        line_end=idx,
                        signature=stripped.rstrip("{").strip(),
                    )
                )
                continue

            java_method = RE_JAVA_METHOD.match(stripped)
            if java_method:
                symbols.append(
                    ExtractedSymbol(
                        name=java_method.group(1),
                        kind="method",
                        line_start=idx,
                        line_end=idx,
                        signature=stripped.rstrip("{").strip(),
                    )
                )
                continue

            # SQL schema definitions
            sql_create = RE_SQL_CREATE.match(stripped)
            if sql_create:
                symbols.append(
                    ExtractedSymbol(
                        name=sql_create.group(1).replace('"', ""),
                        kind="table",
                        line_start=idx,
                        line_end=idx,
                        signature=stripped,
                    )
                )
                continue

        return ParseResult(symbols=symbols, dependencies=dependencies, status="parsed")
