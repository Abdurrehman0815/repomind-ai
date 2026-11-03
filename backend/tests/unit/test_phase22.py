from __future__ import annotations

import pytest
from app.agents.debugging_agent import DebuggingAgent


class Gateway:
    def __init__(self): self.calls = []
    async def call(self, tool_name, arguments):
        self.calls.append(tool_name)
        return {"results": []}


class FakeAnswerer:
    def __init__(self): self.problem = None
    async def answer(self, *, project_id, query, system_prompt, instructions):
        self.problem = query
        return "Likely cause: user_id missing [app/auth.py:L10-L12]", [{"file_path": "app/auth.py", "start_line": 10, "end_line": 12}]


@pytest.mark.asyncio
async def test_stack_trace_diagnosis_uses_search_symbols_and_dependencies():
    gateway, answerer = Gateway(), FakeAnswerer()
    problem = "KeyError: user_id\n  File app/auth.py"
    result = await DebuggingAgent(answerer=answerer, gateway=gateway).diagnose(project_id="p1", session_id="s1", problem=problem)
    assert gateway.calls == ["repo_search", "repo_get_symbols", "repo_get_dependencies"]
    # The full problem text, not a template, drives the grounded answer.
    assert answerer.problem == problem
    assert "app/auth.py" in result["answer"]
    assert result["sources"] and result["confidence"] == "medium"
