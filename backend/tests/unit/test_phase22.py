from __future__ import annotations

import pytest
from app.agents.debugging_agent import DebuggingAgent


class Gateway:
    def __init__(self): self.calls = []
    async def call(self, tool_name, arguments):
        self.calls.append(tool_name)
        return {"results": []}


@pytest.mark.asyncio
async def test_stack_trace_diagnosis_uses_search_symbols_and_dependencies():
    gateway = Gateway()
    result = await DebuggingAgent(gateway=gateway).diagnose(project_id="p1", session_id="s1", problem="KeyError: user_id\n  File app/auth.py")
    assert gateway.calls == ["repo_search", "repo_get_symbols", "repo_get_dependencies"]
    assert "focused regression test" in result["answer"]
