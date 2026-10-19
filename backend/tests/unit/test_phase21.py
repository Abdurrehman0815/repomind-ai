"""Phase 21 benchmark using a sample checkout requirement."""
from __future__ import annotations

import pytest

from app.agents.test_plan_agent import TestPlanAgent


class FakeGateway:
    async def call(self, tool_name: str, arguments: dict):
        return {"results": [{"file_path": "app/checkout.py"}]} if tool_name == "repo_search" else {"files": [{"relative_path": "tests/test_checkout.py"}]}


@pytest.mark.asyncio
async def test_checkout_plan_contains_every_required_coverage_category():
    result = await TestPlanAgent(gateway=FakeGateway()).create_test_plan(
        project_id="p1", session_id="s1", requirement="Add checkout with payment confirmation"
    )
    assert set(result["test_plan"]) == {"unit", "integration", "api", "edge", "security", "regression"}
    assert "checkout" in result["answer"].lower()
    assert result["metadata"]["context_available"] is True


@pytest.mark.asyncio
async def test_plan_remains_actionable_when_context_tools_fail():
    class BrokenGateway:
        async def call(self, tool_name: str, arguments: dict):
            raise RuntimeError("repository unavailable")
    result = await TestPlanAgent(gateway=BrokenGateway()).create_test_plan(project_id="p1", session_id="s1", requirement="Add checkout")
    assert result["confidence"] == "low"
    assert all(result["test_plan"].values())
