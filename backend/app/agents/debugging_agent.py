"""Phase 22: evidence-oriented debugging workflow."""
from __future__ import annotations

from typing import Any

from app.agents.grounding import Answerer
from app.agents.tool_using_agent import FastMCPToolGateway, ToolGateway

SYSTEM_PROMPT = """You are RepoMind AI's Debugging Agent.
Diagnose problems using only the provided repository code. You must:
1. Name the most likely root cause(s), each tied to specific code with a citation
2. Separate what the code shows from what you infer
3. Give concrete steps to confirm the cause and the smallest safe fix
4. Never invent files, functions or behaviour not present in the evidence
5. Never edit files; describe fixes as proposals for the user to approve"""

INSTRUCTIONS = """Structure the answer as:
- Likely cause (with citations)
- How to confirm it (a focused reproduction or regression test)
- Suggested fix (smallest change, as a proposal)
Keep it concise and specific to this code."""


class DebuggingAgent:
    def __init__(self, answerer: Answerer, gateway: ToolGateway | None = None) -> None:
        self.answerer = answerer
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
                await self.gateway.call(tool, args)
                trace.append({"tool": tool, "arguments": args, "status": "success"})
            except Exception as exc:
                trace.append({"tool": tool, "arguments": args, "status": "error", "error": str(exc)})

        answer, sources = await self.answerer.answer(
            project_id=project_id, query=problem, system_prompt=SYSTEM_PROMPT, instructions=INSTRUCTIONS
        )
        return {
            "answer": answer,
            "confidence": "medium" if sources else "low",
            "sources": sources,
            "analysis_type": "debugging",
            "metadata": {"tool_trace": trace, "session_id": session_id},
        }

    @staticmethod
    def _query(problem: str) -> str:
        lines = [line.strip() for line in problem.splitlines() if line.strip()]
        return " ".join(lines[:2])[:200] or "debugging failure"
