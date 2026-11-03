"""Phase 21: evidence-aware test planning grounded in the repository's code."""
from __future__ import annotations

import re
from typing import Any

from app.agents.grounding import Answerer
from app.agents.tool_using_agent import FastMCPToolGateway, ToolGateway

CATEGORIES = {
    "unit": "Unit",
    "integration": "Integration",
    "api": "API",
    "edge": "Edge cases",
    "security": "Security",
    "regression": "Regression",
}

SYSTEM_PROMPT = """You are RepoMind AI's Test Plan Agent.
Write test plans using only the provided repository code. You must:
1. Name the real functions, files and endpoints under test, with citations
2. Prefer concrete test cases (inputs and expected results) over generic advice
3. Never invent code that is not in the evidence; say what is missing instead"""

INSTRUCTIONS = (
    "Write the test plan as exactly these six sections, each a heading line followed by '- ' bullet test cases:\n"
    + "\n".join(f"{heading}:" for heading in CATEGORIES.values())
    + "\nGive 1-4 concrete cases per section."
)


class TestPlanAgent:
    """Create a practical test plan for a feature or requirement."""

    __test__ = False  # Prevent pytest from mistaking this production class for a test case.

    def __init__(self, answerer: Answerer, gateway: ToolGateway | None = None) -> None:
        self.answerer = answerer
        self.gateway = gateway or FastMCPToolGateway()

    async def create_test_plan(self, *, project_id: str, requirement: str, session_id: str) -> dict[str, Any]:
        trace: list[dict[str, Any]] = []
        context = await self._context(project_id, requirement, trace)
        feature = requirement.strip() or "the requested feature"
        answer, sources = await self.answerer.answer(
            project_id=project_id,
            query=f"Test plan for: {feature}",
            system_prompt=SYSTEM_PROMPT,
            instructions=INSTRUCTIONS,
        )
        return {
            "answer": answer,
            "confidence": "medium" if context and sources else "low",
            "sources": sources,
            "analysis_type": "test_plan",
            "test_plan": parse_sections(answer),
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


def parse_sections(answer: str) -> dict[str, list[str]]:
    """Split the model's answer into the six category lists by heading."""
    by_heading = {heading.lower(): key for key, heading in CATEGORIES.items()}
    plan: dict[str, list[str]] = {key: [] for key in CATEGORIES}
    current: str | None = None
    for raw in answer.splitlines():
        line = raw.strip()
        heading = re.sub(r"[#*:\s]+$", "", re.sub(r"^[#*\s]+", "", line)).lower()
        if heading in by_heading:
            current = by_heading[heading]
        elif current and line.startswith(("-", "*")) and len(line) > 2:
            plan[current].append(line.lstrip("-* ").strip())
    return plan
