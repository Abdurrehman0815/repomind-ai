"""Phase 21 benchmark using a sample checkout requirement."""
from __future__ import annotations

import pytest

from app.agents.test_plan_agent import TestPlanAgent, parse_sections


class FakeGateway:
    async def call(self, tool_name: str, arguments: dict):
        return {"results": [{"file_path": "app/checkout.py"}]} if tool_name == "repo_search" else {"files": [{"relative_path": "tests/test_checkout.py"}]}


class FakeAnswerer:
    """Stands in for retrieval + LLM; returns a model-shaped grounded plan."""

    def __init__(self) -> None:
        self.queries: list[str] = []

    async def answer(self, *, project_id, query, system_prompt, instructions):
        self.queries.append(query)
        text = "\n".join(
            f"**{heading}:**\n- checkout case for {heading.lower()} [app/checkout.py:L1-L20]"
            for heading in ("Unit", "Integration", "API", "Edge cases", "Security", "Regression")
        )
        return text, [{"file_path": "app/checkout.py", "start_line": 1, "end_line": 20}]


@pytest.mark.asyncio
async def test_checkout_plan_contains_every_required_coverage_category():
    answerer = FakeAnswerer()
    result = await TestPlanAgent(answerer=answerer, gateway=FakeGateway()).create_test_plan(
        project_id="p1", session_id="s1", requirement="Add checkout with payment confirmation"
    )
    assert set(result["test_plan"]) == {"unit", "integration", "api", "edge", "security", "regression"}
    assert all(result["test_plan"].values())
    assert "checkout" in result["answer"].lower()
    assert result["sources"][0]["file_path"] == "app/checkout.py"
    assert result["metadata"]["context_available"] is True
    assert answerer.queries == ["Test plan for: Add checkout with payment confirmation"]


@pytest.mark.asyncio
async def test_plan_confidence_is_low_when_context_tools_fail():
    class BrokenGateway:
        async def call(self, tool_name: str, arguments: dict):
            raise RuntimeError("repository unavailable")
    result = await TestPlanAgent(answerer=FakeAnswerer(), gateway=BrokenGateway()).create_test_plan(
        project_id="p1", session_id="s1", requirement="Add checkout"
    )
    assert result["confidence"] == "low"
    assert [entry["status"] for entry in result["metadata"]["tool_trace"]] == ["error", "error"]


def test_parse_sections_handles_markdown_headings():
    plan = parse_sections("## Unit\n- a\n- b\nSecurity:\n* c\nnoise line")
    assert plan["unit"] == ["a", "b"] and plan["security"] == ["c"] and plan["api"] == []
