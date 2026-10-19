"""Phase 19 security benchmark for controlled test and linter execution."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.agents.tool_using_agent import ToolUsingAgent
from app.models.project import Project
from app.repositories.project_repository import ProjectRepository
from app.security import SecurityError
from app.tools.execution_tools import run_tests


@pytest.fixture
def execution_repo(tmp_path: Path) -> Path:
    """Create a minimal repository used only by execution-security tests."""
    repo = tmp_path / "execution_repo"
    (repo / "tests").mkdir(parents=True)
    (repo / "tests" / "test_main.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    return repo


@pytest.fixture
async def execution_project(test_db_session, execution_repo: Path) -> Project:
    return await ProjectRepository(test_db_session).create(name="Execution Project", path=str(execution_repo))


class TestSafeExecutionSelection:
    def test_execution_requires_explicit_confirmation(self):
        agent = ToolUsingAgent()
        assert agent.select_execution_tools(project_id="p1", query="Run the tests", user_confirmed=False) == []

    def test_confirmed_test_request_uses_only_pytest(self):
        agent = ToolUsingAgent()
        plan = agent.select_execution_tools(project_id="p1", query="Run the tests", user_confirmed=True)
        assert len(plan) == 1
        assert plan[0].name == "run_tests"
        assert plan[0].arguments == {"project_id": "p1", "test_framework": "pytest"}

    def test_confirmed_lint_request_uses_only_ruff(self):
        agent = ToolUsingAgent()
        plan = agent.select_execution_tools(project_id="p1", query="Run Ruff", user_confirmed=True)
        assert len(plan) == 1
        assert plan[0].name == "run_linter"
        assert plan[0].arguments["linter"] == "ruff"


class TestSafeExecutionToolInput:
    @pytest.mark.asyncio
    async def test_pytest_path_option_injection_is_rejected(self, execution_project, test_db_session):
        with pytest.raises(SecurityError, match="not a command option"):
            await run_tests(
                project_id=execution_project.id,
                test_framework="pytest",
                path="-k malicious_expression",
                db_session=test_db_session,
            )

    @pytest.mark.asyncio
    async def test_targeted_npm_test_is_rejected(self, execution_project, test_db_session):
        with pytest.raises(SecurityError, match="only for pytest"):
            await run_tests(
                project_id=execution_project.id,
                test_framework="npm_test",
                path="tests",
                db_session=test_db_session,
            )

    @pytest.mark.asyncio
    async def test_pytest_target_is_a_validated_literal_path(self, execution_project, test_db_session):
        with patch("app.tools.execution_tools.execute_command_safely", new_callable=AsyncMock) as execute:
            execute.return_value = {"status": "success", "exit_code": 0, "stdout": "1 passed", "stderr": "", "duration_ms": 1, "truncated": False}
            await run_tests(
                project_id=execution_project.id,
                test_framework="pytest",
                path="tests/test_main.py",
                db_session=test_db_session,
            )
            assert execute.call_args.kwargs["cmd"] == ["python", "-m", "pytest", "tests/test_main.py"]
