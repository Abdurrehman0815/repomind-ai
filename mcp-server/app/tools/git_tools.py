"""
RepoMind AI — MCP Git Tools

Provides safe, controlled Git inspection operations:
- git_status: inspect working tree changes
- git_diff: inspect unstaged or staged diffs (optionally filtered by file)
- git_log: inspect recent commit history

Security guarantees:
- shell=False strictly enforced
- allowlisted git subcommands only
- paths strictly validated against repository boundaries
- execution timeout and output character caps
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from .repo_tools import resolve_project
from ..security import execute_command_safely, validate_repo_path

logger = structlog.get_logger(__name__)


async def git_status(
    project_id: str,
    db_session: Optional[AsyncSession] = None,
) -> dict[str, Any]:
    """
    Get git status for the repository.
    """
    project = await resolve_project(project_id, db_session)
    repo_root = Path(project.path).resolve()

    res = await execute_command_safely(
        cmd=["git", "status"],
        cwd=repo_root,
        timeout_seconds=30,
    )
    return {
        "project_id": project.id,
        "project_path": project.path,
        "tool": "git_status",
        **res,
    }


async def git_diff(
    project_id: str,
    file_path: Optional[str] = None,
    staged: bool = False,
    db_session: Optional[AsyncSession] = None,
) -> dict[str, Any]:
    """
    Get git diff for the repository or a specific file.
    """
    project = await resolve_project(project_id, db_session)
    repo_root = Path(project.path).resolve()

    cmd = ["git", "diff"]
    if staged:
        cmd.append("--staged")

    if file_path and file_path.strip():
        # Validate that the file path does not escape the repo
        target_path = validate_repo_path(repo_root, file_path)
        rel = target_path.relative_to(repo_root).as_posix()
        cmd.extend(["--", rel])

    res = await execute_command_safely(
        cmd=cmd,
        cwd=repo_root,
        timeout_seconds=30,
    )
    return {
        "project_id": project.id,
        "project_path": project.path,
        "file_path": file_path,
        "staged": staged,
        "tool": "git_diff",
        **res,
    }


async def git_log(
    project_id: str,
    max_count: int = 10,
    db_session: Optional[AsyncSession] = None,
) -> dict[str, Any]:
    """
    Get recent git commit log for the repository.
    """
    count = max(1, min(max_count, 100))
    project = await resolve_project(project_id, db_session)
    repo_root = Path(project.path).resolve()

    res = await execute_command_safely(
        cmd=["git", "log", f"-n{count}", "--oneline"],
        cwd=repo_root,
        timeout_seconds=30,
    )
    return {
        "project_id": project.id,
        "project_path": project.path,
        "max_count": count,
        "tool": "git_log",
        **res,
    }
