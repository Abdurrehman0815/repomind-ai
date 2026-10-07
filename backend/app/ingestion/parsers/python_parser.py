"""
RepoMind AI — Python AST Code Parser

Uses the Python standard library 'ast' module for high-fidelity symbol extraction,
signature synthesis, docstring extraction, and hierarchical class-method mapping.
Includes resilient fallback on syntax errors.
"""
from __future__ import annotations

import ast
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


def _format_arg(arg: ast.arg, default: ast.expr | None = None) -> str:
    """Format a single function parameter with type annotation and default."""
    res = arg.arg
    if arg.annotation:
        try:
            res += f": {ast.unparse(arg.annotation)}"
        except Exception:
            pass
    if default:
        try:
            res += f" = {ast.unparse(default)}"
        except Exception:
            pass
    return res


def _format_function_signature(
    node: ast.FunctionDef | ast.AsyncFunctionDef, is_method: bool = False
) -> str:
    """Reconstruct function or method signature from AST node."""
    prefix = "async def " if isinstance(node, ast.AsyncFunctionDef) else "def "
    args_list: list[str] = []

    # Position-only args (Python 3.8+)
    posonly_defaults_offset = len(node.args.posonlyargs) - len(node.args.defaults)
    for i, a in enumerate(node.args.posonlyargs):
        default = None
        if i >= posonly_defaults_offset and posonly_defaults_offset >= 0:
            default = node.args.defaults[i - posonly_defaults_offset]
        args_list.append(_format_arg(a, default))
    if node.args.posonlyargs:
        args_list.append("/")

    # Standard args
    num_defaults = len(node.args.defaults)
    num_standard = len(node.args.args)
    default_offset = num_standard - num_defaults
    for i, a in enumerate(node.args.args):
        default = None
        if i >= default_offset:
            default = node.args.defaults[i - default_offset]
        args_list.append(_format_arg(a, default))

    # *vararg
    if node.args.vararg:
        args_list.append(f"*{_format_arg(node.args.vararg)}")

    # Keyword-only args
    for a, d in zip(node.args.kwonlyargs, node.args.kw_defaults):
        args_list.append(_format_arg(a, d))

    # **kwarg
    if node.args.kwarg:
        args_list.append(f"**{_format_arg(node.args.kwarg)}")

    sig = f"{prefix}{node.name}({', '.join(args_list)})"
    if node.returns:
        try:
            sig += f" -> {ast.unparse(node.returns)}"
        except Exception:
            pass
    return sig


class PythonCodeParser(BaseCodeParser):
    """AST parser for Python files."""

    def can_parse(self, language: str) -> bool:
        return language.lower() in {"python", "py"}

    def parse(self, code: str, file_path: str = "") -> ParseResult:
        if not code or not code.strip():
            return ParseResult(symbols=[], dependencies=[], status="parsed")

        try:
            tree = ast.parse(code, filename=file_path)
            return self._parse_ast(tree)
        except SyntaxError as syn_err:
            logger.warning(
                "python_ast_syntax_error_fallback",
                path=file_path,
                line=syn_err.lineno,
                error=str(syn_err),
            )
            return self._fallback_regex_parse(code, error=str(syn_err))
        except Exception as exc:
            logger.error("python_parse_failed", path=file_path, error=str(exc))
            return self._fallback_regex_parse(code, error=str(exc))

    def _parse_ast(self, tree: ast.AST) -> ParseResult:
        symbols: list[ExtractedSymbol] = []
        dependencies: list[ExtractedDependency] = []

        for node in ast.iter_child_nodes(tree):
            # 1. Imports
            if isinstance(node, ast.Import):
                for alias in node.names:
                    dependencies.append(
                        ExtractedDependency(
                            module=alias.name,
                            symbol_name=alias.asname or alias.name,
                            raw_statement=f"import {alias.name}",
                            line_number=node.lineno,
                        )
                    )
            elif isinstance(node, ast.ImportFrom):
                mod_name = node.module or ""
                for alias in node.names:
                    dependencies.append(
                        ExtractedDependency(
                            module=mod_name,
                            symbol_name=alias.name,
                            raw_statement=f"from {mod_name} import {alias.name}",
                            line_number=node.lineno,
                        )
                    )

            # 2. Classes
            elif isinstance(node, ast.ClassDef):
                bases: list[str] = []
                for b in node.bases:
                    try:
                        bases.append(ast.unparse(b))
                    except Exception:
                        pass
                class_sig = f"class {node.name}" + (f"({', '.join(bases)})" if bases else "")

                class_sym = ExtractedSymbol(
                    name=node.name,
                    kind="class",
                    line_start=node.lineno,
                    line_end=getattr(node, "end_lineno", node.lineno),
                    signature=class_sig,
                    docstring=ast.get_docstring(node),
                )
                symbols.append(class_sym)

                # Class methods
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        method_sig = _format_function_signature(item, is_method=True)
                        method_sym = ExtractedSymbol(
                            name=item.name,
                            kind="method",
                            line_start=item.lineno,
                            line_end=getattr(item, "end_lineno", item.lineno),
                            signature=method_sig,
                            docstring=ast.get_docstring(item),
                            parent_name=node.name,
                        )
                        symbols.append(method_sym)

            # 3. Top-level Functions
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                func_sig = _format_function_signature(node, is_method=False)
                func_sym = ExtractedSymbol(
                    name=node.name,
                    kind="function",
                    line_start=node.lineno,
                    line_end=getattr(node, "end_lineno", node.lineno),
                    signature=func_sig,
                    docstring=ast.get_docstring(node),
                )
                symbols.append(func_sym)

        return ParseResult(symbols=symbols, dependencies=dependencies, status="parsed")

    def _fallback_regex_parse(self, code: str, error: str) -> ParseResult:
        """Heuristic regex scanner for files with syntax errors."""
        symbols: list[ExtractedSymbol] = []
        dependencies: list[ExtractedDependency] = []
        lines = code.splitlines()

        for idx, line in enumerate(lines, start=1):
            stripped = line.strip()

            # Class declaration
            class_match = re.match(r"class\s+([a-zA-Z_0-9]+)", stripped)
            if class_match:
                symbols.append(
                    ExtractedSymbol(
                        name=class_match.group(1),
                        kind="class",
                        line_start=idx,
                        line_end=idx,
                        signature=stripped,
                    )
                )

            # Function/method declaration
            func_match = re.match(r"(?:async\s+)?def\s+([a-zA-Z_0-9]+)", stripped)
            if func_match:
                is_indented = len(line) - len(line.lstrip()) > 0
                symbols.append(
                    ExtractedSymbol(
                        name=func_match.group(1),
                        kind="method" if is_indented else "function",
                        line_start=idx,
                        line_end=idx,
                        signature=stripped,
                    )
                )

            # Import statement
            import_match = re.match(r"(?:from\s+([a-zA-Z_0-9.]+)\s+)?import\s+([a-zA-Z_0-9.*, ]+)", stripped)
            if import_match:
                mod = import_match.group(1) or import_match.group(2).split(",")[0].strip()
                dependencies.append(
                    ExtractedDependency(
                        module=mod,
                        raw_statement=stripped,
                        line_number=idx,
                    )
                )

        return ParseResult(
            symbols=symbols,
            dependencies=dependencies,
            status="partial",
            error_message=f"Syntax error, parsed with fallback: {error}",
        )
