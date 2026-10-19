"""
RepoMind AI — MCP Execution Tools

Provides safe, sandboxed execution of developer testing and linting tools:
- run_tests: run allowlisted test runners (pytest, npm test)
- run_linter: run allowlisted code linters (ruff, mypy, npm run lint)

Security guarantees:
- Strict command allowlists only — arbitrary commands and flags rejected
- shell=False strictly enforced
- working directory pinned to repository root
- execution timeout (default 60s) with hard termination
- output capped at 50,000 characters
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from .repo_tools import resolve_project
from ..security import SecurityError, execute_command_safely, validate_repo_path

logger = structlog.get_logger(__name__)

SUPPORTED_TEST_FRAMEWORKS: dict[str, list[str]] = {
    "pytest": ["python", "-m", "pytest"],
    "npm_test": ["npm", "test"],
}

SUPPORTED_LINTERS: dict[str, list[str]] = {
    "ruff": ["python", "-m", "ruff", "check"],
    "mypy": ["python", "-m", "mypy"],
    "npm_lint": ["npm", "run", "lint"],
}


def _validate_test_target(repo_root: Path, path: str) -> str:
    """Return a safe relative pytest target, rejecting option injection."""
    requested = path.strip()
    if requested.startswith("-"):
        raise SecurityError("Test target must be a repository path, not a command option")
    target_path = validate_repo_path(repo_root, requested)
    if not target_path.exists():
        raise FileNotFoundError(f"Test target does not exist: '{requested}'")
    return target_path.relative_to(repo_root).as_posix()


async def run_tests(
    project_id: str,
    test_framework: str = "pytest",
    path: Optional[str] = None,
    timeout_seconds: int = 60,
    db_session: Optional[AsyncSession] = None,
) -> dict[str, Any]:
    """
    Run allowlisted test suite in the repository.
    """
    fw = test_framework.strip().lower()
    if fw not in SUPPORTED_TEST_FRAMEWORKS:
        raise SecurityError(
            f"Unsupported test framework '{test_framework}'. Allowed frameworks: {list(SUPPORTED_TEST_FRAMEWORKS.keys())}"
        )

    timeout = max(5, min(timeout_seconds, 300))
    project = await resolve_project(project_id, db_session)
    repo_root = Path(project.path).resolve()

    cmd = list(SUPPORTED_TEST_FRAMEWORKS[fw])

    if path and path.strip():
        if fw != "pytest":
            raise SecurityError("Targeted paths are supported only for pytest")
        cmd.append(_validate_test_target(repo_root, path))

    res = await execute_command_safely(
        cmd=cmd,
        cwd=repo_root,
        timeout_seconds=timeout,
    )

    return {
        "project_id": project.id,
        "project_path": project.path,
        "test_framework": fw,
        "path": path,
        "tool": "run_tests",
        **res,
    }


async def run_linter(
    project_id: str,
    linter: str = "ruff",
    timeout_seconds: int = 60,
    db_session: Optional[AsyncSession] = None,
) -> dict[str, Any]:
    """
    Run allowlisted code linter in the repository.
    """
    lt = linter.strip().lower()
    if lt not in SUPPORTED_LINTERS:
        raise SecurityError(
            f"Unsupported linter '{linter}'. Allowed linters: {list(SUPPORTED_LINTERS.keys())}"
        )

    timeout = max(5, min(timeout_seconds, 300))
    project = await resolve_project(project_id, db_session)
    repo_root = Path(project.path).resolve()

    cmd = list(SUPPORTED_LINTERS[lt])

    res = await execute_command_safely(
        cmd=cmd,
        cwd=repo_root,
        timeout_seconds=timeout,
    )

    return {
        "project_id": project.id,
        "project_path": project.path,
        "linter": lt,
        "tool": "run_linter",
        **res,
    }
