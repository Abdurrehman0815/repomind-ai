"""
RepoMind AI — TypeScript and JavaScript Code Parser

Extracts classes, methods, functions, arrow function components, interfaces, types,
enums, JSDoc comments, and ES/CommonJS imports with accurate line boundaries.
"""
from __future__ import annotations

import re
import structlog
from typing import Any

from app.ingestion.parsers.base import (
    BaseCodeParser,
    ExtractedSymbol,
    ExtractedDependency,
    ParseResult,
)

logger = structlog.get_logger(__name__)

# Regular expressions for JS/TS constructs
RE_IMPORT = re.compile(
    r"""(?:import\s+(?:(?:[\w*\s{},$]+)\s+from\s+)?['"]([^'"]+)['"]|require\s*\(\s*['"]([^'"]+)['"]\s*\))"""
)
RE_CLASS = re.compile(
    r"^(?:export\s+(?:default\s+)?)?class\s+([a-zA-Z_$][a-zA-Z0-9_$]*)"
)
RE_INTERFACE = re.compile(
    r"^(?:export\s+)?interface\s+([a-zA-Z_$][a-zA-Z0-9_$]*)"
)
RE_TYPE = re.compile(
    r"^(?:export\s+)?type\s+([a-zA-Z_$][a-zA-Z0-9_$]*)\s*="
)
RE_ENUM = re.compile(
    r"^(?:export\s+)?enum\s+([a-zA-Z_$][a-zA-Z0-9_$]*)"
)
RE_FUNCTION = re.compile(
    r"^(?:export\s+(?:default\s+)?)?(?:async\s+)?function(?:\s+([a-zA-Z_$][a-zA-Z0-9_$]*))?\s*\("
)
RE_ARROW_FUNC = re.compile(
    r"^(?:export\s+)?(?:const|let|var)\s+([a-zA-Z_$][a-zA-Z0-9_$]*)\s*=\s*(?:async\s*)?(?:\([^)]*\)|[a-zA-Z_$][a-zA-Z0-9_$]*)\s*=>"
)
RE_METHOD = re.compile(
    r"^(?:(?:public|private|protected|static|async|override)\s+)*([a-zA-Z_$][a-zA-Z0-9_$]*)\s*\([^)]*\)\s*(?::\s*[^{]+)?\s*\{"
)


class TypeScriptJavaScriptParser(BaseCodeParser):
    """Parser for TypeScript, TSX, JavaScript, and JSX source files."""

    def can_parse(self, language: str) -> bool:
        return language.lower() in {
            "typescript",
            "typescriptreact",
            "javascript",
            "javascriptreact",
            "ts",
            "tsx",
            "js",
            "jsx",
        }

    def parse(self, code: str, file_path: str = "") -> ParseResult:
        if not code or not code.strip():
            return ParseResult(symbols=[], dependencies=[], status="parsed")

        symbols: list[ExtractedSymbol] = []
        dependencies: list[ExtractedDependency] = []
        lines = code.splitlines()

        current_class: str | None = None
        brace_depth = 0
        class_brace_depth = 0
        jsdoc_buffer: list[str] = []

        for idx, line in enumerate(lines, start=1):
            stripped = line.strip()

            # JSDoc comment accumulation
            if stripped.startswith("/**") or stripped.startswith("*") or stripped.endswith("*/"):
                jsdoc_buffer.append(stripped)
            elif not stripped.startswith("//") and stripped:
                # Line has code; see if we have accumulated JSDoc
                docstring = "\n".join(jsdoc_buffer) if jsdoc_buffer else None
                jsdoc_buffer = []

                # 1. Imports
                imp_match = RE_IMPORT.search(stripped)
                if imp_match:
                    mod = imp_match.group(1) or imp_match.group(2)
                    if mod:
                        dependencies.append(
                            ExtractedDependency(
                                module=mod,
                                raw_statement=stripped,
                                line_number=idx,
                            )
                        )

                # 2. Class declaration
                class_match = RE_CLASS.match(stripped)
                if class_match:
                    class_name = class_match.group(1)
                    current_class = class_name
                    class_brace_depth = brace_depth + (line.count("{") - line.count("}"))
                    symbols.append(
                        ExtractedSymbol(
                            name=class_name,
                            kind="class",
                            line_start=idx,
                            line_end=idx,  # Updated as braces close
                            signature=stripped.rstrip("{").strip(),
                            docstring=docstring,
                        )
                    )

                # 3. Interface declaration
                int_match = RE_INTERFACE.match(stripped)
                if int_match:
                    symbols.append(
                        ExtractedSymbol(
                            name=int_match.group(1),
                            kind="interface",
                            line_start=idx,
                            line_end=idx,
                            signature=stripped.rstrip("{").strip(),
                            docstring=docstring,
                        )
                    )

                # 4. Type alias
                type_match = RE_TYPE.match(stripped)
                if type_match:
                    symbols.append(
                        ExtractedSymbol(
                            name=type_match.group(1),
                            kind="type",
                            line_start=idx,
                            line_end=idx,
                            signature=stripped,
                            docstring=docstring,
                        )
                    )

                # 5. Enum
                enum_match = RE_ENUM.match(stripped)
                if enum_match:
                    symbols.append(
                        ExtractedSymbol(
                            name=enum_match.group(1),
                            kind="enum",
                            line_start=idx,
                            line_end=idx,
                            signature=stripped.rstrip("{").strip(),
                            docstring=docstring,
                        )
                    )

                # 6. Top-level or exported function
                func_match = RE_FUNCTION.match(stripped)
                if func_match and not current_class:
                    fname = func_match.group(1) or "anonymous"
                    symbols.append(
                        ExtractedSymbol(
                            name=fname,
                            kind="function",
                            line_start=idx,
                            line_end=idx,
                            signature=stripped.rstrip("{").strip(),
                            docstring=docstring,
                        )
                    )

                # 7. Arrow function / Functional Component
                arrow_match = RE_ARROW_FUNC.match(stripped)
                if arrow_match and not current_class:
                    symbols.append(
                        ExtractedSymbol(
                            name=arrow_match.group(1),
                            kind="function",
                            line_start=idx,
                            line_end=idx,
                            signature=stripped.rstrip("{").strip(),
                            docstring=docstring,
                        )
                    )

                # 8. Class Method
                if current_method_match := (RE_METHOD.match(stripped) if current_class else None):
                    mname = current_method_match.group(1)
                    if mname not in {"if", "for", "while", "switch", "catch"}:
                        symbols.append(
                            ExtractedSymbol(
                                name=mname,
                                kind="method",
                                line_start=idx,
                                line_end=idx,
                                signature=stripped.rstrip("{").strip(),
                                docstring=docstring,
                                parent_name=current_class,
                            )
                        )

            # Brace tracking for class scoping
            brace_depth += line.count("{") - line.count("}")
            if current_class and brace_depth < class_brace_depth:
                current_class = None

        return ParseResult(symbols=symbols, dependencies=dependencies, status="parsed")
