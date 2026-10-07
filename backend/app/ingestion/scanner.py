"""
RepoMind AI — Repository File Scanner & Language Detector

Traverses a local repository, enforces security constraints, respects .gitignore,
filters binaries/large files, computes cryptographic hashes, and maps file languages.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Generator, NamedTuple

import pathspec
import structlog

logger = structlog.get_logger(__name__)

# Extensions mapped to language identifiers
LANGUAGE_MAP: dict[str, str] = {
    ".py": "python",
    ".pyw": "python",
    ".ts": "typescript",
    ".tsx": "typescriptreact",
    ".js": "javascript",
    ".jsx": "javascriptreact",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".hpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".cs": "csharp",
    ".rb": "ruby",
    ".php": "php",
    ".swift": "swift",
    ".kt": "kotlin",
    ".scala": "scala",
    ".html": "html",
    ".htm": "html",
    ".css": "css",
    ".scss": "scss",
    ".sass": "sass",
    ".less": "less",
    ".sql": "sql",
    ".sh": "shell",
    ".bash": "shell",
    ".zsh": "shell",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".xml": "xml",
    ".md": "markdown",
    ".markdown": "markdown",
    ".txt": "text",
    ".rst": "rst",
    ".dockerfile": "dockerfile",
}

# Explicit filenames to language
EXPLICIT_FILENAMES: dict[str, str] = {
    "dockerfile": "dockerfile",
    "makefile": "makefile",
    "gemfile": "ruby",
    "rakefile": "ruby",
    "cmakelists.txt": "cmake",
}

# Standard directories and files ignored by default
DEFAULT_IGNORES: list[str] = [
    ".git",
    ".git/*",
    ".svn",
    ".hg",
    "node_modules",
    "node_modules/*",
    "__pycache__",
    "__pycache__/*",
    "*.pyc",
    "*.pyo",
    ".venv",
    ".venv/*",
    "venv",
    "venv/*",
    "env",
    "env/*",
    "dist",
    "dist/*",
    "build",
    "build/*",
    ".next",
    ".next/*",
    ".nuxt",
    ".nuxt/*",
    "out",
    "target",
    "target/*",
    ".idea",
    ".idea/*",
    ".vscode",
    ".vscode/*",
    ".pytest_cache",
    ".pytest_cache/*",
    ".ruff_cache",
    ".ruff_cache/*",
    ".mypy_cache",
    ".mypy_cache/*",
    "coverage",
    "coverage/*",
    ".nyc_output",
    ".DS_Store",
    "Thumbs.db",
]

# Extensions known to be non-text binaries
BINARY_EXTENSIONS: set[str] = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".webp", ".bmp", ".tiff",
    ".pdf", ".zip", ".tar", ".gz", ".tgz", ".7z", ".rar", ".bz2", ".xz",
    ".exe", ".dll", ".so", ".dylib", ".bin", ".iso", ".dat",
    ".mp3", ".mp4", ".wav", ".avi", ".mov", ".mkv", ".flac",
    ".woff", ".woff2", ".ttf", ".otf", ".eot",
    ".pyc", ".pyo", ".pyd", ".class", ".jar", ".war",
    ".db", ".sqlite", ".sqlite3",
}


class ScannedFileInfo(NamedTuple):
    """Metadata for an ingested file."""
    absolute_path: str
    relative_path: str
    file_hash: str
    language: str
    size_bytes: int
    line_count: int


def detect_language(path: Path) -> str | None:
    """Detect language from file name or extension. Returns None if unknown/binary."""
    file_name = path.name.lower()
    if file_name in EXPLICIT_FILENAMES:
        return EXPLICIT_FILENAMES[file_name]

    ext = path.suffix.lower()
    if ext in BINARY_EXTENSIONS:
        return None

    return LANGUAGE_MAP.get(ext, None)


def compute_file_hash(path: Path) -> str:
    """Compute SHA-256 hash of file contents."""
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def count_lines_and_size(path: Path) -> tuple[int, int]:
    """Return line count and size in bytes for a text file."""
    size = path.stat().st_size
    line_count = 0
    with open(path, "rb") as f:
        for line in f:
            line_count += 1
    return line_count, size


def load_gitignore_spec(repo_dir: Path) -> pathspec.PathSpec:
    """
    Compile ignore patterns from default rules and .gitignore/.ignore files.
    """
    patterns: list[str] = list(DEFAULT_IGNORES)

    gitignore_path = repo_dir / ".gitignore"
    if gitignore_path.is_file():
        try:
            with open(gitignore_path, "r", encoding="utf-8", errors="ignore") as f:
                patterns.extend(f.read().splitlines())
        except Exception as exc:
            logger.warning("failed_reading_gitignore", error=str(exc))

    ignore_path = repo_dir / ".ignore"
    if ignore_path.is_file():
        try:
            with open(ignore_path, "r", encoding="utf-8", errors="ignore") as f:
                patterns.extend(f.read().splitlines())
        except Exception as exc:
            logger.warning("failed_reading_ignore", error=str(exc))

    return pathspec.PathSpec.from_lines("gitwildmatch", patterns)


def scan_repository(
    repo_path: str | Path,
    max_file_size_bytes: int = 1_048_576,  # 1 MB default limit
) -> Generator[ScannedFileInfo, None, None]:
    """
    Scan a repository directory safely.

    Security guarantees:
    - Resolves real canonical paths to defend against symlink loops and escapes.
    - Skips symlinks whose targets resolve outside the repository tree.
    - Enforces maximum file size limit to prevent memory/storage denial of service.
    - Yields ScannedFileInfo objects for valid text source files.
    """
    root = Path(repo_path).resolve()
    if not root.exists():
        raise FileNotFoundError(f"Repository path does not exist: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"Repository path is not a directory: {root}")

    spec = load_gitignore_spec(root)

    for dirpath, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
        current_dir = Path(dirpath)

        # Compute relative directory path for ignore checking
        try:
            rel_dir = current_dir.relative_to(root).as_posix()
        except ValueError:
            continue

        # Prune ignored directories in-place to avoid descending into them
        pruned_dirs: list[str] = []
        for d in dirnames:
            candidate_rel = f"{rel_dir}/{d}" if rel_dir != "." else d
            # Also append trailing slash for gitwildmatch directory matching
            if spec.match_file(candidate_rel) or spec.match_file(f"{candidate_rel}/"):
                continue
            pruned_dirs.append(d)
        dirnames[:] = pruned_dirs

        for f in filenames:
            file_path = current_dir / f

            # Symlink safety check: if symlink, verify target resides inside root
            if file_path.is_symlink():
                try:
                    resolved_target = file_path.resolve()
                    if not resolved_target.is_relative_to(root):
                        logger.warning("skipping_external_symlink", path=str(file_path))
                        continue
                except (OSError, ValueError):
                    continue

            # Compute relative path
            try:
                rel_file = file_path.relative_to(root).as_posix()
            except ValueError:
                continue

            # Check ignore spec
            if spec.match_file(rel_file):
                continue

            # Language check
            lang = detect_language(file_path)
            if not lang:
                continue

            # Size limit check
            try:
                file_size = file_path.stat().st_size
                if file_size > max_file_size_bytes or file_size == 0:
                    continue
            except OSError:
                continue

            # Compute hash and line count
            try:
                line_count, size_bytes = count_lines_and_size(file_path)
                f_hash = compute_file_hash(file_path)
            except (OSError, UnicodeDecodeError):
                continue

            yield ScannedFileInfo(
                absolute_path=str(file_path.resolve()),
                relative_path=rel_file,
                file_hash=f_hash,
                language=lang,
                size_bytes=size_bytes,
                line_count=line_count,
            )
