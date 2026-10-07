"""
RepoMind AI — Parsers Package and Registry
"""
from app.ingestion.parsers.base import (
    BaseCodeParser,
    ExtractedSymbol,
    ExtractedDependency,
    ParseResult,
)
from app.ingestion.parsers.python_parser import PythonCodeParser
from app.ingestion.parsers.ts_js_parser import TypeScriptJavaScriptParser
from app.ingestion.parsers.generic_parser import GenericMultiLanguageParser

_PYTHON_PARSER = PythonCodeParser()
_TS_JS_PARSER = TypeScriptJavaScriptParser()
_GENERIC_PARSER = GenericMultiLanguageParser()


def get_parser_for_language(language: str) -> BaseCodeParser:
    """Resolve the appropriate code parser for a given programming language."""
    lang = language.lower()
    if _PYTHON_PARSER.can_parse(lang):
        return _PYTHON_PARSER
    if _TS_JS_PARSER.can_parse(lang):
        return _TS_JS_PARSER
    return _GENERIC_PARSER


def parse_file_content(language: str, content: str, file_path: str = "") -> ParseResult:
    """Convenience function to parse source text using the resolved parser."""
    parser = get_parser_for_language(language)
    return parser.parse(content, file_path=file_path)


__all__ = [
    "BaseCodeParser",
    "ExtractedSymbol",
    "ExtractedDependency",
    "ParseResult",
    "PythonCodeParser",
    "TypeScriptJavaScriptParser",
    "GenericMultiLanguageParser",
    "get_parser_for_language",
    "parse_file_content",
]
