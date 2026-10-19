"""Phase 18 tool-selection benchmark for the controlled MCP agent."""
from __future__ import annotations

import pytest

from app.agents.tool_using_agent import ToolUsingAgent


class FakeGateway:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def call(self, tool_name: str, arguments: dict):
        self.calls.append((tool_name, arguments))
        if tool_name == "repo_search":
            return {"results": [{"file_path": "src/auth/login.py"}]}
        if tool_name == "repo_read_file":
            return {"file_path": arguments["file_path"], "content": "def login(): pass"}
        return {"total_found": 0}


def test_debugging_query_selects_repository_evidence_tools():
    agent = ToolUsingAgent(gateway=FakeGateway())
    plan = agent.select_tools(project_id="project-1", query="Why is login failing?", intent="debugging")
    assert [call.name for call in plan] == ["repo_search", "repo_get_symbols", "repo_search"]
    assert plan[0].arguments["query"] == "login"
    assert plan[1].arguments["name"] == "login"


def test_architecture_query_selects_repository_map_and_dependencies():
    agent = ToolUsingAgent(gateway=FakeGateway())
    plan = agent.select_tools(project_id="project-1", query="Explain the authentication flow", intent="architecture_explanation")
    assert [call.name for call in plan] == ["repo_list_files", "repo_search", "repo_get_dependencies"]


def test_greeting_does_not_select_tools():
    agent = ToolUsingAgent(gateway=FakeGateway())
    assert agent.select_tools(project_id="project-1", query="hello", intent="general_question") == []


@pytest.mark.asyncio
async def test_search_results_trigger_bounded_file_inspection():
    agent = ToolUsingAgent(gateway=FakeGateway())
    trace = await agent.investigate(project_id="project-1", query="Why is login failing?", intent="debugging")
    names = [record["tool"] for record in trace]
    assert "repo_read_file" in names
    assert names.count("repo_read_file") == 1
    assert all(record["status"] == "success" for record in trace)
