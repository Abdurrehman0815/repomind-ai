"""
RepoMind AI — Model Context Protocol (MCP) Server

Exposes controlled repository intelligence and developer execution tools:
- repo_list_files: Browse files in local repository
- repo_read_file: Read file contents safely with line range support
- repo_search: Hybrid semantic + keyword code search
- repo_get_symbols: Extract AST code symbols and hierarchy
- repo_get_dependencies: Query file and project module dependencies
- git_status: Inspect working directory changes
- git_diff: Inspect uncommitted or staged changes
- git_log: Inspect recent commit history
- run_tests: Safely run pytest / npm test suites
- run_linter: Safely run ruff / mypy / npm lint

All tools call the internal backend service and repository layers without duplicating business logic.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Optional

# Ensure backend root is on sys.path
CURRENT_FILE = Path(__file__).resolve()
REPO_ROOT = CURRENT_FILE.parent.parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Ensure mcp-server root is on sys.path
MCP_SERVER_DIR = CURRENT_FILE.parent.parent
if str(MCP_SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(MCP_SERVER_DIR))

from mcp.server.fastmcp import FastMCP
import structlog

from .tools.execution_tools import run_linter as _run_linter, run_tests as _run_tests
from .tools.git_tools import git_diff as _git_diff, git_log as _git_log, git_status as _git_status
from .tools.repo_tools import (
    repo_get_dependencies as _repo_get_dependencies,
    repo_get_symbols as _repo_get_symbols,
    repo_list_files as _repo_list_files,
    repo_read_file as _repo_read_file,
    repo_search as _repo_search,
)

logger = structlog.get_logger(__name__)


def create_mcp_server() -> FastMCP:
    """Create and configure the RepoMind FastMCP server with all tools."""
    mcp = FastMCP("RepoMind MCP Server")

    @mcp.tool()
    async def repo_list_files(
        project_id: str,
        directory: str = ".",
        recursive: bool = True,
        limit: int = 100,
    ) -> str:
        """
        List files in repository respecting .gitignore, exclusions, and path security.

        Args:
            project_id: UUID of project, registered path, or valid repository directory.
            directory: Relative directory inside the repository (default: '.').
            recursive: Whether to list subdirectories recursively (default: True).
            limit: Maximum files to return (default: 100, max: 1000).
        """
        try:
            res = await _repo_list_files(
                project_id=project_id,
                directory=directory,
                recursive=recursive,
                limit=limit,
            )
            return json.dumps(res, indent=2)
        except Exception as exc:
            logger.error("mcp_tool_error", tool="repo_list_files", error=str(exc))
            return json.dumps({"error": str(exc), "tool": "repo_list_files"}, indent=2)

    @mcp.tool()
    async def repo_read_file(
        project_id: str,
        file_path: str,
        start_line: Optional[int] = None,
        end_line: Optional[int] = None,
    ) -> str:
        """
        Safely read contents of a file within the repository, with optional line range.

        Args:
            project_id: UUID of project, registered path, or valid repository directory.
            file_path: Relative path to the target file.
            start_line: Optional 1-indexed start line.
            end_line: Optional 1-indexed end line.
        """
        try:
            res = await _repo_read_file(
                project_id=project_id,
                file_path=file_path,
                start_line=start_line,
                end_line=end_line,
            )
            return json.dumps(res, indent=2)
        except Exception as exc:
            logger.error("mcp_tool_error", tool="repo_read_file", error=str(exc))
            return json.dumps({"error": str(exc), "tool": "repo_read_file"}, indent=2)

    @mcp.tool()
    async def repo_search(
        project_id: str,
        query: str,
        limit: int = 10,
        file_id: Optional[str] = None,
        language: Optional[str] = None,
    ) -> str:
        """
        Search indexed repository using hybrid vector and keyword search.

        Args:
            project_id: UUID of project, registered path, or valid repository directory.
            query: Natural language or code search term.
            limit: Maximum results to return (default: 10, max: 50).
            file_id: Optional filter by specific file ID.
            language: Optional filter by programming language.
        """
        try:
            res = await _repo_search(
                project_id=project_id,
                query=query,
                limit=limit,
                file_id=file_id,
                language=language,
            )
            return json.dumps(res, indent=2)
        except Exception as exc:
            logger.error("mcp_tool_error", tool="repo_search", error=str(exc))
            return json.dumps({"error": str(exc), "tool": "repo_search"}, indent=2)

    @mcp.tool()
    async def repo_get_symbols(
        project_id: str,
        file_path: Optional[str] = None,
        name: Optional[str] = None,
        kind: Optional[str] = None,
        limit: int = 50,
    ) -> str:
        """
        Get extracted AST code symbols for a project, file, symbol name, or symbol kind.

        Args:
            project_id: UUID of project, registered path, or valid repository directory.
            file_path: Optional relative path of file to inspect.
            name: Optional symbol name substring filter.
            kind: Optional symbol kind ('function', 'class', 'method', 'interface').
            limit: Maximum symbols to return (default: 50, max: 200).
        """
        try:
            res = await _repo_get_symbols(
                project_id=project_id,
                file_path=file_path,
                name=name,
                kind=kind,
                limit=limit,
            )
            return json.dumps(res, indent=2)
        except Exception as exc:
            logger.error("mcp_tool_error", tool="repo_get_symbols", error=str(exc))
            return json.dumps({"error": str(exc), "tool": "repo_get_symbols"}, indent=2)

    @mcp.tool()
    async def repo_get_dependencies(
        project_id: str,
        file_path: Optional[str] = None,
        limit: int = 50,
    ) -> str:
        """
        Get dependencies and import edges for a project or specific file.

        Args:
            project_id: UUID of project, registered path, or valid repository directory.
            file_path: Optional relative path of file to inspect.
            limit: Maximum dependencies to return (default: 50, max: 200).
        """
        try:
            res = await _repo_get_dependencies(
                project_id=project_id,
                file_path=file_path,
                limit=limit,
            )
            return json.dumps(res, indent=2)
        except Exception as exc:
            logger.error("mcp_tool_error", tool="repo_get_dependencies", error=str(exc))
            return json.dumps({"error": str(exc), "tool": "repo_get_dependencies"}, indent=2)

    @mcp.tool()
    async def git_status(project_id: str) -> str:
        """
        Get git working tree status for the repository.

        Args:
            project_id: UUID of project, registered path, or valid repository directory.
        """
        try:
            res = await _git_status(project_id=project_id)
            return json.dumps(res, indent=2)
        except Exception as exc:
            logger.error("mcp_tool_error", tool="git_status", error=str(exc))
            return json.dumps({"error": str(exc), "tool": "git_status"}, indent=2)

    @mcp.tool()
    async def git_diff(
        project_id: str,
        file_path: Optional[str] = None,
        staged: bool = False,
    ) -> str:
        """
        Get git diff for the repository or a specific file.

        Args:
            project_id: UUID of project, registered path, or valid repository directory.
            file_path: Optional relative path of file to diff.
            staged: Whether to view staged changes (default: False).
        """
        try:
            res = await _git_diff(
                project_id=project_id,
                file_path=file_path,
                staged=staged,
            )
            return json.dumps(res, indent=2)
        except Exception as exc:
            logger.error("mcp_tool_error", tool="git_diff", error=str(exc))
            return json.dumps({"error": str(exc), "tool": "git_diff"}, indent=2)

    @mcp.tool()
    async def git_log(
        project_id: str,
        max_count: int = 10,
    ) -> str:
        """
        Get recent git commit log for the repository.

        Args:
            project_id: UUID of project, registered path, or valid repository directory.
            max_count: Maximum number of commits to list (default: 10, max: 100).
        """
        try:
            res = await _git_log(
                project_id=project_id,
                max_count=max_count,
            )
            return json.dumps(res, indent=2)
        except Exception as exc:
            logger.error("mcp_tool_error", tool="git_log", error=str(exc))
            return json.dumps({"error": str(exc), "tool": "git_log"}, indent=2)

    @mcp.tool()
    async def run_tests(
        project_id: str,
        test_framework: str = "pytest",
        path: Optional[str] = None,
    ) -> str:
        """
        Safely run allowlisted test suites in the repository.

        Args:
            project_id: UUID of project, registered path, or valid repository directory.
            test_framework: Allowlisted framework ('pytest' or 'npm_test').
            path: Optional test file or directory path relative to repository.
        """
        try:
            res = await _run_tests(
                project_id=project_id,
                test_framework=test_framework,
                path=path,
            )
            return json.dumps(res, indent=2)
        except Exception as exc:
            logger.error("mcp_tool_error", tool="run_tests", error=str(exc))
            return json.dumps({"error": str(exc), "tool": "run_tests"}, indent=2)

    @mcp.tool()
    async def run_linter(
        project_id: str,
        linter: str = "ruff",
    ) -> str:
        """
        Safely run allowlisted code linters in the repository.

        Args:
            project_id: UUID of project, registered path, or valid repository directory.
            linter: Allowlisted linter ('ruff', 'mypy', or 'npm_lint').
        """
        try:
            res = await _run_linter(
                project_id=project_id,
                linter=linter,
            )
            return json.dumps(res, indent=2)
        except Exception as exc:
            logger.error("mcp_tool_error", tool="run_linter", error=str(exc))
            return json.dumps({"error": str(exc), "tool": "run_linter"}, indent=2)

    return mcp


# Default singleton instance
server = create_mcp_server()

if __name__ == "__main__":
    server.run()
