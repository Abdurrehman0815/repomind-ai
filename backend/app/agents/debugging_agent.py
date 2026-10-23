"""Phase 22: evidence-oriented debugging workflow."""
from __future__ import annotations

from typing import Any

from app.agents.tool_using_agent import FastMCPToolGateway, ToolGateway


class DebuggingAgent:
    def __init__(self, gateway: ToolGateway | None = None) -> None:
        self.gateway = gateway or FastMCPToolGateway()

    async def diagnose(self, *, project_id: str, problem: str, session_id: str) -> dict[str, Any]:
        trace: list[dict[str, Any]] = []
        query = self._query(problem)
        for tool, args in (
            ("repo_search", {"project_id": project_id, "query": query, "limit": 8}),
            ("repo_get_symbols", {"project_id": project_id, "name": query.split()[0], "limit": 20}),
            ("repo_get_dependencies", {"project_id": project_id, "limit": 50}),
        ):
            try:
                result = await self.gateway.call(tool, args)
                trace.append({"tool": tool, "arguments": args, "status": "success"})
            except Exception as exc:
                trace.append({"tool": tool, "arguments": args, "status": "error", "error": str(exc)})
        evidence = [entry for entry in trace if entry["status"] == "success"]
        answer = (
            f"Debugging plan for: {problem}\n"
            "- Reproduce the failure with the smallest input.\n"
            "- Inspect the retrieved symbol and its dependency path.\n"
            "- Confirm the failing condition with a focused regression test.\n"
            "- Apply the smallest source-grounded fix, then rerun the focused and adjacent tests."
        )
        return {"answer": answer, "confidence": "medium" if evidence else "low", "sources": [], "analysis_type": "debugging", "metadata": {"tool_trace": trace, "session_id": session_id}}

    @staticmethod
    def _query(problem: str) -> str:
        lines = [line.strip() for line in problem.splitlines() if line.strip()]
        return " ".join(lines[:2])[:200] or "debugging failure"
