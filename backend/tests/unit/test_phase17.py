"""
RepoMind AI — Phase 17 Unit Tests: Model Context Protocol (MCP) Server & Tools

Tests each MCP tool independently:
1. repo_list_files
2. repo_read_file
3. repo_search
4. repo_get_symbols
5. repo_get_dependencies
6. git_status
7. git_diff
8. git_log
9. run_tests
10. run_linter

Verification criteria:
- Input schema validation
- Path security (path traversal, absolute paths, sensitive file blocking)
- Command allowlist enforcement (no arbitrary shell injection)
- Timeout control and hard termination
- Output character caps and error handling
- FastMCP tool registration and invocation
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# Ensure mcp-server is available on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
MCP_SERVER_DIR = REPO_ROOT / "mcp-server"
if str(MCP_SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(MCP_SERVER_DIR))

import pytest

from app.models.code_chunk import CodeChunk
from app.models.code_symbol import CodeSymbol
from app.models.dependency import Dependency
from app.models.file_document import FileDocument
from app.models.project import Project
from app.repositories.dependency_repository import DependencyRepository
from app.repositories.file_repository import FileRepository
from app.repositories.project_repository import ProjectRepository
from app.repositories.symbol_repository import SymbolRepository
from app.security import (
    SecurityError,
    execute_command_safely,
    is_sensitive_path,
    validate_repo_path,
)

# Import MCP tools directly
from app.tools.execution_tools import run_linter, run_tests
from app.tools.git_tools import git_diff, git_log, git_status
from app.tools.repo_tools import (
    repo_get_dependencies,
    repo_get_symbols,
    repo_list_files,
    repo_read_file,
    repo_search,
    resolve_project,
)
from app.server import create_mcp_server, server


# ── Fixtures ──────────────────────────────────────────────────

@pytest.fixture
def sample_repo(tmp_path: Path) -> Path:
    """Create a temporary git repository with mock files and sensitive files."""
    repo = tmp_path / "sample_repo"
    repo.mkdir()

    # Create source files
    src = repo / "src"
    src.mkdir()
    (src / "main.py").write_text("def main():\n    print('Hello World')\n\nif __name__ == '__main__':\n    main()\n", encoding="utf-8")
    (src / "utils.py").write_text("def add(a, b):\n    return a + b\n\ndef sub(a, b):\n    return a - b\n", encoding="utf-8")

    # Create test directory and file
    tests = repo / "tests"
    tests.mkdir()
    (tests / "test_main.py").write_text("def test_dummy():\n    assert True\n", encoding="utf-8")

    # Create sensitive files that must be protected
    (repo / ".env").write_text("SECRET_KEY=supersecret\n", encoding="utf-8")
    (repo / "id_rsa").write_text("-----BEGIN RSA PRIVATE KEY-----\n", encoding="utf-8")

    return repo


@pytest.fixture
async def indexed_project(test_db_session, sample_repo: Path) -> Project:
    """Seed test database with project, files, symbols, and dependencies."""
    project_repo = ProjectRepository(test_db_session)
    file_repo = FileRepository(test_db_session)
    symbol_repo = SymbolRepository(test_db_session)
    dep_repo = DependencyRepository(test_db_session)

    # 1. Project
    project = await project_repo.create(
        name="Sample Project",
        path=str(sample_repo),
    )

    # 2. Files
    file_main = await file_repo.create(
        project_id=project.id,
        path=str(sample_repo / "src" / "main.py"),
        relative_path="src/main.py",
        file_hash="hash_main",
        language="python",
        size_bytes=80,
        line_count=5,
    )
    file_utils = await file_repo.create(
        project_id=project.id,
        path=str(sample_repo / "src" / "utils.py"),
        relative_path="src/utils.py",
        file_hash="hash_utils",
        language="python",
        size_bytes=60,
        line_count=5,
    )

    # 3. Symbols
    await symbol_repo.create(
        project_id=project.id,
        file_id=file_main.id,
        name="main",
        kind="function",
        line_start=1,
        line_end=2,
        signature="def main()",
        docstring="Main entrypoint function",
    )
    await symbol_repo.create(
        project_id=project.id,
        file_id=file_utils.id,
        name="add",
        kind="function",
        line_start=1,
        line_end=2,
        signature="def add(a, b)",
        docstring="Add two numbers",
    )

    # 4. Dependencies
    dep = Dependency(
        project_id=project.id,
        source_file_id=file_main.id,
        target_file_id=file_utils.id,
        target_module="src.utils",
        import_statement="from src.utils import add",
        symbol_name="add",
        line_number=1,
    )
    test_db_session.add(dep)
    await test_db_session.flush()

    return project


# ── Security Tests ────────────────────────────────────────────

class TestSecurityControls:
    """Verifies path traversal defenses, sensitive file exclusions, and command allowlists."""

    def test_sensitive_file_detection(self):
        assert is_sensitive_path(".env")
        assert is_sensitive_path(".env.local")
        assert is_sensitive_path("id_rsa")
        assert is_sensitive_path("certs/server.key")
        assert is_sensitive_path("secrets.json")
        assert not is_sensitive_path("src/main.py")
        assert not is_sensitive_path("README.md")

    def test_validate_repo_path_safe(self, sample_repo: Path):
        p = validate_repo_path(sample_repo, "src/main.py")
        assert p.exists()
        assert p == (sample_repo / "src" / "main.py").resolve()

    def test_validate_repo_path_traversal_rejection(self, sample_repo: Path):
        with pytest.raises(SecurityError, match="Path traversal detected"):
            validate_repo_path(sample_repo, "../../windows/system32")

    def test_validate_repo_path_absolute_rejection(self, sample_repo: Path):
        with pytest.raises(SecurityError, match="Absolute paths not permitted"):
            validate_repo_path(sample_repo, "C:/Windows/System32")

    def test_validate_repo_path_sensitive_rejection(self, sample_repo: Path):
        with pytest.raises(SecurityError, match="Access to sensitive file or pattern is forbidden"):
            validate_repo_path(sample_repo, ".env")

    @pytest.mark.asyncio
    async def test_command_execution_timeout(self, tmp_path: Path):
        # Run command with 1s timeout on a slow command
        res = await execute_command_safely(
            cmd=["python", "-c", "import time; time.sleep(5)"],
            cwd=tmp_path,
            timeout_seconds=1,
        )
        assert res["status"] == "timeout"
        assert res["exit_code"] == -1
        assert "timed out" in res["stderr"]

    @pytest.mark.asyncio
    async def test_command_output_capping(self, tmp_path: Path):
        # Generate 10,000 characters with cap of 500
        res = await execute_command_safely(
            cmd=["python", "-c", "print('A' * 10000)"],
            cwd=tmp_path,
            timeout_seconds=5,
            max_output_chars=500,
        )
        assert res["status"] == "success"
        assert res["truncated"] is True
        assert len(res["stdout"]) < 1000
        assert "truncated" in res["stdout"].lower()


# ── Repository Tools Tests ────────────────────────────────────

class TestRepoTools:
    """Verifies repo_list_files, repo_read_file, repo_search, repo_get_symbols, repo_get_dependencies."""

    @pytest.mark.asyncio
    async def test_repo_list_files_basic(self, indexed_project: Project, test_db_session):
        res = await repo_list_files(
            project_id=indexed_project.id,
            directory=".",
            recursive=True,
            db_session=test_db_session,
        )
        assert res["project_id"] == indexed_project.id
        assert res["total_found"] >= 2
        file_paths = [f["relative_path"] for f in res["files"]]
        assert "src/main.py" in file_paths
        assert "src/utils.py" in file_paths
        # Sensitive files must NOT be listed
        assert ".env" not in file_paths
        assert "id_rsa" not in file_paths

    @pytest.mark.asyncio
    async def test_repo_list_files_traversal_defense(self, indexed_project: Project, test_db_session):
        with pytest.raises(SecurityError, match="Path traversal detected"):
            await repo_list_files(
                project_id=indexed_project.id,
                directory="../..",
                db_session=test_db_session,
            )

    @pytest.mark.asyncio
    async def test_repo_read_file_full(self, indexed_project: Project, test_db_session):
        res = await repo_read_file(
            project_id=indexed_project.id,
            file_path="src/main.py",
            db_session=test_db_session,
        )
        assert res["file_path"] == "src/main.py"
        assert "def main():" in res["content"]
        assert res["total_lines"] == 5

    @pytest.mark.asyncio
    async def test_repo_read_file_line_range(self, indexed_project: Project, test_db_session):
        res = await repo_read_file(
            project_id=indexed_project.id,
            file_path="src/main.py",
            start_line=1,
            end_line=2,
            db_session=test_db_session,
        )
        assert res["start_line"] == 1
        assert res["end_line"] == 2
        assert "def main():" in res["content"]
        assert "if __name__" not in res["content"]

    @pytest.mark.asyncio
    async def test_repo_read_file_sensitive_blocked(self, indexed_project: Project, test_db_session):
        with pytest.raises(SecurityError, match="Access to sensitive file or pattern is forbidden"):
            await repo_read_file(
                project_id=indexed_project.id,
                file_path=".env",
                db_session=test_db_session,
            )

    @pytest.mark.asyncio
    async def test_repo_read_file_invalid_range_raises(self, indexed_project: Project, test_db_session):
        with pytest.raises(ValueError, match="cannot be greater than end_line"):
            await repo_read_file(
                project_id=indexed_project.id,
                file_path="src/main.py",
                start_line=10,
                end_line=2,
                db_session=test_db_session,
            )

    @pytest.mark.asyncio
    async def test_repo_search(self, indexed_project: Project, test_db_session):
        # Mock retrieval service hybrid_search
        mock_chunk = MagicMock(spec=CodeChunk)
        mock_chunk.id = "chunk-123"
        mock_chunk.file_id = "nonexistent"
        mock_chunk.start_line = 1
        mock_chunk.end_line = 10
        mock_chunk.content = "def test_chunk(): pass"

        with patch("app.tools.repo_tools.RetrievalService") as MockService:
            instance = MockService.return_value
            instance.hybrid_search = AsyncMock(return_value=[(mock_chunk, 0.95)])

            res = await repo_search(
                project_id=indexed_project.id,
                query="test_chunk",
                limit=5,
                db_session=test_db_session,
            )
            assert res["query"] == "test_chunk"
            assert res["total_found"] == 1
            assert res["results"][0]["chunk_id"] == "chunk-123"
            assert res["results"][0]["score"] == 0.95

    @pytest.mark.asyncio
    async def test_repo_get_symbols(self, indexed_project: Project, test_db_session):
        res = await repo_get_symbols(
            project_id=indexed_project.id,
            db_session=test_db_session,
        )
        assert res["total_symbols"] == 2
        names = [s["name"] for s in res["symbols"]]
        assert "main" in names
        assert "add" in names

    @pytest.mark.asyncio
    async def test_repo_get_symbols_filtered_by_file(self, indexed_project: Project, test_db_session):
        res = await repo_get_symbols(
            project_id=indexed_project.id,
            file_path="src/utils.py",
            db_session=test_db_session,
        )
        assert res["total_symbols"] == 1
        assert res["symbols"][0]["name"] == "add"

    @pytest.mark.asyncio
    async def test_repo_get_dependencies(self, indexed_project: Project, test_db_session):
        res = await repo_get_dependencies(
            project_id=indexed_project.id,
            db_session=test_db_session,
        )
        assert res["total_dependencies"] == 1
        dep = res["dependencies"][0]
        assert dep["target_module"] == "src.utils"
        assert dep["source_file"] == "src/main.py"
        assert dep["target_file"] == "src/utils.py"


# ── Git Tools Tests ───────────────────────────────────────────

class TestGitTools:
    """Verifies git_status, git_diff, and git_log."""

    @pytest.mark.asyncio
    async def test_git_status_mocked(self, indexed_project: Project, test_db_session):
        with patch("app.tools.git_tools.execute_command_safely") as mock_exec:
            mock_exec.return_value = {
                "status": "success",
                "exit_code": 0,
                "stdout": "On branch main\nnothing to commit, working tree clean",
                "stderr": "",
                "duration_ms": 15,
                "truncated": False,
            }
            res = await git_status(
                project_id=indexed_project.id,
                db_session=test_db_session,
            )
            assert res["tool"] == "git_status"
            assert res["status"] == "success"
            assert "On branch main" in res["stdout"]

    @pytest.mark.asyncio
    async def test_git_diff_mocked(self, indexed_project: Project, test_db_session):
        with patch("app.tools.git_tools.execute_command_safely") as mock_exec:
            mock_exec.return_value = {
                "status": "success",
                "exit_code": 0,
                "stdout": "diff --git a/src/main.py b/src/main.py\n+ # change",
                "stderr": "",
                "duration_ms": 20,
                "truncated": False,
            }
            res = await git_diff(
                project_id=indexed_project.id,
                file_path="src/main.py",
                staged=False,
                db_session=test_db_session,
            )
            assert res["tool"] == "git_diff"
            assert res["file_path"] == "src/main.py"
            assert "diff --git" in res["stdout"]

    @pytest.mark.asyncio
    async def test_git_diff_traversal_rejection(self, indexed_project: Project, test_db_session):
        with pytest.raises(SecurityError, match="Path traversal detected"):
            await git_diff(
                project_id=indexed_project.id,
                file_path="../../etc/passwd",
                db_session=test_db_session,
            )

    @pytest.mark.asyncio
    async def test_git_log_mocked(self, indexed_project: Project, test_db_session):
        with patch("app.tools.git_tools.execute_command_safely") as mock_exec:
            mock_exec.return_value = {
                "status": "success",
                "exit_code": 0,
                "stdout": "a1b2c3d initial commit\n",
                "stderr": "",
                "duration_ms": 12,
                "truncated": False,
            }
            res = await git_log(
                project_id=indexed_project.id,
                max_count=5,
                db_session=test_db_session,
            )
            assert res["tool"] == "git_log"
            assert res["max_count"] == 5
            assert "initial commit" in res["stdout"]


# ── Execution Tools Tests ─────────────────────────────────────

class TestExecutionTools:
    """Verifies run_tests and run_linter with allowlists and safety."""

    @pytest.mark.asyncio
    async def test_run_tests_pytest_mocked(self, indexed_project: Project, test_db_session):
        with patch("app.tools.execution_tools.execute_command_safely") as mock_exec:
            mock_exec.return_value = {
                "status": "success",
                "exit_code": 0,
                "stdout": "== 1 passed in 0.05s ==",
                "stderr": "",
                "duration_ms": 150,
                "truncated": False,
            }
            res = await run_tests(
                project_id=indexed_project.id,
                test_framework="pytest",
                path="tests/test_main.py",
                db_session=test_db_session,
            )
            assert res["tool"] == "run_tests"
            assert res["test_framework"] == "pytest"
            assert res["status"] == "success"
            # Verify command arguments passed
            called_cmd = mock_exec.call_args[1]["cmd"]
            assert called_cmd[:3] == ["python", "-m", "pytest"]
            assert called_cmd[3] == "tests/test_main.py"

    @pytest.mark.asyncio
    async def test_run_tests_disallowed_framework(self, indexed_project: Project, test_db_session):
        with pytest.raises(SecurityError, match="Unsupported test framework"):
            await run_tests(
                project_id=indexed_project.id,
                test_framework="bash_runner",
                db_session=test_db_session,
            )

    @pytest.mark.asyncio
    async def test_run_linter_ruff_mocked(self, indexed_project: Project, test_db_session):
        with patch("app.tools.execution_tools.execute_command_safely") as mock_exec:
            mock_exec.return_value = {
                "status": "success",
                "exit_code": 0,
                "stdout": "All checks passed!",
                "stderr": "",
                "duration_ms": 80,
                "truncated": False,
            }
            res = await run_linter(
                project_id=indexed_project.id,
                linter="ruff",
                db_session=test_db_session,
            )
            assert res["tool"] == "run_linter"
            assert res["linter"] == "ruff"
            assert res["status"] == "success"
            called_cmd = mock_exec.call_args[1]["cmd"]
            assert called_cmd == ["python", "-m", "ruff", "check"]

    @pytest.mark.asyncio
    async def test_run_linter_disallowed_linter(self, indexed_project: Project, test_db_session):
        with pytest.raises(SecurityError, match="Unsupported linter"):
            await run_linter(
                project_id=indexed_project.id,
                linter="arbitrary_eval",
                db_session=test_db_session,
            )


# ── FastMCP Server Integration Tests ──────────────────────────

class TestFastMCPServerIntegration:
    """Verifies FastMCP server initialization, registered tool count, and discovery."""

    def test_mcp_server_registers_all_10_tools(self):
        mcp = create_mcp_server()
        tool_names = [t.name for t in mcp._tool_manager.list_tools()]

        expected_tools = [
            "repo_list_files",
            "repo_read_file",
            "repo_search",
            "repo_get_symbols",
            "repo_get_dependencies",
            "git_status",
            "git_diff",
            "git_log",
            "run_tests",
            "run_linter",
        ]

        for expected in expected_tools:
            assert expected in tool_names, f"Tool {expected} missing from MCP server"

    @pytest.mark.asyncio
    async def test_mcp_tool_execution_via_server(self, sample_repo: Path):
        mcp = create_mcp_server()
        tool = mcp._tool_manager.get_tool("repo_list_files")
        assert tool is not None

        # Call tool via server's tool manager
        raw_result = await tool.fn(
            project_id=str(sample_repo),
            directory=".",
            recursive=True,
            limit=50,
        )
        parsed = json.loads(raw_result)
        assert "files" in parsed
        assert parsed["total_found"] >= 2
