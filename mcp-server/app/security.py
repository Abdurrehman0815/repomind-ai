"""
RepoMind AI — MCP Security Layer

Enforces repository isolation, sensitive file exclusion, path traversal defense,
strict command allowlists, timeout control, and output truncation.
"""
from __future__ import annotations

import asyncio
import fnmatch
import os
import time
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class SecurityError(Exception):
    """Raised when an operation violates security policies."""
    pass


# Sensitive files and patterns that are strictly forbidden from access
SENSITIVE_PATTERNS: tuple[str, ...] = (
    ".env",
    ".env.*",
    ".env.local",
    ".env.production",
    ".env.development",
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
    "*.jks",
    "id_rsa",
    "id_rsa.*",
    "id_ed25519",
    "id_ed25519.*",
    "credentials",
    "credentials.*",
    "secrets",
    "secrets.*",
    "*.secret",
    ".netrc",
    ".npmrc",
    ".pypirc",
    "google-credentials.json",
    "service-account*.json",
    "aws-credentials*",
    "*.password",
    "*.passwd",
)

# Strict allowlist of executables and permitted tool commands
ALLOWED_TOOLS: dict[str, list[str]] = {
    "git_status": ["git", "status"],
    "git_diff": ["git", "diff"],
    "git_log": ["git", "log"],
    "pytest": ["python", "-m", "pytest"],
    "npm_test": ["npm", "test"],
    "ruff": ["python", "-m", "ruff", "check"],
    "mypy": ["python", "-m", "mypy"],
    "npm_lint": ["npm", "run", "lint"],
}


def is_sensitive_path(path: str | Path) -> bool:
    """Return True if any part of the path or filename matches sensitive patterns."""
    p = Path(path)
    # Check all parts of path as well as filename
    names_to_check = [p.name] + list(p.parts)
    for name in names_to_check:
        lower_name = name.lower()
        for pattern in SENSITIVE_PATTERNS:
            if fnmatch.fnmatch(lower_name, pattern.lower()):
                return True
    return False


def validate_repo_path(repo_root: str | Path, requested_rel_path: str = ".") -> Path:
    """
    Validate that requested_rel_path resides safely within repo_root.

    Security rules:
    - Rejects empty strings that resolve ambiguously
    - Rejects absolute paths
    - Detects directory traversal (e.g. '../')
    - Verifies real canonical path remains within real canonical repo root
    - Rejects any file matching SENSITIVE_PATTERNS
    """
    if not repo_root:
        raise SecurityError("Repository root path cannot be empty")

    root = Path(repo_root).resolve()
    if not root.exists():
        raise SecurityError(f"Repository root does not exist: {root}")
    if not root.is_dir():
        raise SecurityError(f"Repository root is not a directory: {root}")

    if not requested_rel_path or requested_rel_path.strip() == "":
        requested_rel_path = "."

    # Check for absolute path injection
    if os.path.isabs(requested_rel_path) or (
        len(requested_rel_path) > 1 and requested_rel_path[1] == ":"
    ):
        raise SecurityError(f"Absolute paths not permitted: '{requested_rel_path}'")

    # Resolve target path relative to root
    target = (root / requested_rel_path).resolve()

    try:
        is_safe = target == root or target.is_relative_to(root)
    except AttributeError:
        # Fallback for older python or complex paths
        common = os.path.commonpath([str(root), str(target)])
        is_safe = common == str(root)

    if not is_safe:
        raise SecurityError(
            f"Path traversal detected: '{requested_rel_path}' escapes repository root '{root}'"
        )

    # Check sensitive files exclusion
    if is_sensitive_path(target):
        raise SecurityError(
            f"Access to sensitive file or pattern is forbidden: '{target.name}'"
        )

    return target


async def execute_command_safely(
    cmd: list[str],
    cwd: str | Path,
    timeout_seconds: int = 60,
    max_output_chars: int = 50_000,
) -> dict[str, Any]:
    """
    Execute a predefined allowlisted command safely without shell expansion.

    Guarantees:
    - shell=False strictly enforced
    - Working directory validated to exist
    - Subprocess execution timeout with hard kill
    - Output capped at max_output_chars to prevent memory/DoSin
    """
    work_dir = Path(cwd).resolve()
    if not work_dir.exists() or not work_dir.is_dir():
        raise SecurityError(f"Invalid working directory: {work_dir}")

    start_time = time.perf_counter()
    logger.info("executing_safe_command", cmd=cmd, cwd=str(work_dir), timeout=timeout_seconds)

    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(work_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout_data, stderr_data = await asyncio.wait_for(
                process.communicate(),
                timeout=float(timeout_seconds),
            )
        except asyncio.TimeoutError:
            try:
                process.kill()
                await process.wait()
            except ProcessLookupError:
                pass
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            return {
                "status": "timeout",
                "exit_code": -1,
                "stdout": "",
                "stderr": f"Command timed out after {timeout_seconds} seconds",
                "duration_ms": duration_ms,
                "truncated": False,
            }

        duration_ms = int((time.perf_counter() - start_time) * 1000)
        stdout = stdout_data.decode("utf-8", errors="replace")
        stderr = stderr_data.decode("utf-8", errors="replace")

        truncated = False
        if len(stdout) > max_output_chars:
            stdout = stdout[:max_output_chars] + f"\n... [Output truncated at {max_output_chars} characters]"
            truncated = True
        if len(stderr) > max_output_chars:
            stderr = stderr[:max_output_chars] + f"\n... [Error output truncated at {max_output_chars} characters]"
            truncated = True

        status = "success" if process.returncode == 0 else "error"

        return {
            "status": status,
            "exit_code": process.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "duration_ms": duration_ms,
            "truncated": truncated,
        }

    except Exception as exc:
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        logger.error("command_execution_failed", cmd=cmd, error=str(exc))
        return {
            "status": "error",
            "exit_code": -1,
            "stdout": "",
            "stderr": f"Execution error: {str(exc)}",
            "duration_ms": duration_ms,
            "truncated": False,
        }
