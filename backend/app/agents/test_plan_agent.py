"""Phase 21: deterministic, evidence-aware test planning."""
from __future__ import annotations

from typing import Any

from app.agents.tool_using_agent import FastMCPToolGateway, ToolGateway


class TestPlanAgent:
    """Create a practical test plan for a feature or requirement."""

    __test__ = False  # Prevent pytest from mistaking this production class for a test case.

    def __init__(self, gateway: ToolGateway | None = None) -> None:
        self.gateway = gateway or FastMCPToolGateway()

    async def create_test_plan(self, *, project_id: str, requirement: str, session_id: str) -> dict[str, Any]:
        trace: list[dict[str, Any]] = []
        context = await self._context(project_id, requirement, trace)
        feature = requirement.strip() or "the requested feature"
        plan = {
            "unit": [f"Validate input parsing and business rules for {feature}.", "Cover successful, invalid, empty, and boundary-value inputs."],
            "integration": [f"Verify {feature} with its persistence and dependent-service boundaries.", "Verify failures from dependencies are surfaced without corrupting state."],
            "api": [f"Test the endpoint or handler that exposes {feature}: success, validation, authorization, and error responses."],
            "edge": ["Test duplicate requests, retries, concurrent requests, and missing optional data.", "Test maximum-size and malformed payloads."],
            "security": ["Verify authentication and authorization boundaries.", "Verify untrusted input cannot access another user’s data or trigger unsafe execution."],
            "regression": ["Add a test for the reported behaviour and preserve existing adjacent workflows.", "Run the relevant existing suite before merging."],
        }
        lines = [f"Test plan for: {feature}"]
        for category, cases in plan.items():
            lines.append(f"\n{category.title()}")
            lines.extend(f"- {case}" for case in cases)
        return {
            "answer": "\n".join(lines), "confidence": "medium" if context else "low", "sources": [],
            "analysis_type": "test_plan", "test_plan": plan,
            "metadata": {"context_available": context, "tool_trace": trace, "session_id": session_id},
        }

    async def _context(self, project_id: str, requirement: str, trace: list[dict[str, Any]]) -> bool:
        for tool, args in (
            ("repo_search", {"project_id": project_id, "query": requirement, "limit": 5}),
            ("repo_list_files", {"project_id": project_id, "directory": "tests", "recursive": True, "limit": 30}),
        ):
            try:
                result = await self.gateway.call(tool, args)
                trace.append({"tool": tool, "arguments": args, "status": "success"})
                if isinstance(result, dict) and (result.get("results") or result.get("files")):
                    return True
            except Exception as exc:
                trace.append({"tool": tool, "arguments": args, "status": "error", "error": str(exc)})
        return False
