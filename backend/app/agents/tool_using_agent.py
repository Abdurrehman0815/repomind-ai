"""Phase 18: controlled MCP tool selection and execution for RepoMind agents.

The agent deliberately uses only repository-inspection tools. Commands that can
execute code are reserved for the later safe-execution phase.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import structlog

logger = structlog.get_logger(__name__)


class ToolGateway(Protocol):
    """Adapter boundary that makes tool selection independently testable."""

    async def call(self, tool_name: str, arguments: dict[str, Any]) -> Any: ...


class FastMCPToolGateway:
    """Invoke a registered FastMCP tool in-process through its tool manager."""

    _MODULE_NAME = "repomind_mcp_server"

    @classmethod
    def _server(cls) -> Any:
        module = sys.modules.get(cls._MODULE_NAME)
        if module is None:
            repository_root = Path(__file__).resolve().parents[3]
            server_path = repository_root / "mcp-server" / "app" / "server.py"
            spec = importlib.util.spec_from_file_location(
                cls._MODULE_NAME,
                server_path,
                submodule_search_locations=[str(server_path.parent)],
            )
            if spec is None or spec.loader is None:
                raise RuntimeError("RepoMind MCP server could not be loaded")
            module = importlib.util.module_from_spec(spec)
            sys.modules[cls._MODULE_NAME] = module
            try:
                spec.loader.exec_module(module)
            except BaseException:
                # Don't cache a half-initialised module; the next call retries cleanly.
                sys.modules.pop(cls._MODULE_NAME, None)
                raise
        return module.create_mcp_server()

    async def call(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        server = self._server()
        tool = server._tool_manager.get_tool(tool_name)
        if tool is None:
            raise ValueError(f"MCP tool is not registered: {tool_name}")
        raw_result = await tool.fn(**arguments)
        return json.loads(raw_result) if isinstance(raw_result, str) else raw_result


@dataclass(frozen=True)
class ToolCall:
    """A transparent, reviewable tool request selected by the agent."""

    name: str
    arguments: dict[str, Any]
    reason: str


class ToolUsingAgent:
    """Choose and use read-only MCP tools for evidence-gathering workflows."""

    def __init__(self, gateway: ToolGateway | None = None) -> None:
        self.gateway = gateway or FastMCPToolGateway()

    def select_tools(self, *, project_id: str, query: str, intent: str) -> list[ToolCall]:
        """Return a deterministic, conservative investigation plan."""
        normalized = query.strip()
        lower = normalized.lower()
        if not normalized or lower in {"hi", "hello", "thanks", "thank you"}:
            return []

        search_query = self._search_terms(normalized)
        if intent == "debugging" or any(word in lower for word in ("failing", "fails", "error", "bug", "broken")):
            symbol_name = self._candidate_symbol(search_query)
            return [
                ToolCall("repo_search", {"project_id": project_id, "query": search_query, "limit": 5}, "Find code related to the failure."),
                ToolCall("repo_get_symbols", {"project_id": project_id, "name": symbol_name, "limit": 20}, "Inspect the relevant callable or class."),
                ToolCall("repo_search", {"project_id": project_id, "query": f"{search_query} test", "limit": 5}, "Find related tests before diagnosing the issue."),
            ]
        if intent == "code_navigation":
            return [
                ToolCall("repo_search", {"project_id": project_id, "query": search_query, "limit": 10}, "Locate relevant source files."),
                ToolCall("repo_get_symbols", {"project_id": project_id, "name": self._candidate_symbol(search_query), "limit": 20}, "Locate matching symbols."),
            ]
        if intent in {"architecture_explanation", "change_impact", "implementation_plan"}:
            return [
                ToolCall("repo_list_files", {"project_id": project_id, "recursive": True, "limit": 100}, "Map the repository before analysing relationships."),
                ToolCall("repo_search", {"project_id": project_id, "query": search_query, "limit": 10}, "Gather source evidence for the request."),
                ToolCall("repo_get_dependencies", {"project_id": project_id, "limit": 50}, "Inspect import and dependency relationships."),
            ]
        if intent == "code_review" or any(word in lower for word in ("diff", "pull request", "review")):
            return [ToolCall("git_diff", {"project_id": project_id}, "Inspect the working-tree changes under review.")]
        return [ToolCall("repo_search", {"project_id": project_id, "query": search_query, "limit": 8}, "Gather repository evidence before answering.")]

    async def investigate(self, *, project_id: str, query: str, intent: str) -> list[dict[str, Any]]:
        """Execute selected tools and return a compact, auditable trace."""
        trace: list[dict[str, Any]] = []
        read_paths: set[str] = set()
        for call in self.select_tools(project_id=project_id, query=query, intent=intent):
            record: dict[str, Any] = {"tool": call.name, "arguments": call.arguments, "reason": call.reason}
            try:
                result = await self.gateway.call(call.name, call.arguments)
                record.update({"status": "success", "summary": self._summarize(result)})
                trace.append(record)
                if call.name == "repo_search" and isinstance(result, dict):
                    for item in result.get("results", []):
                        path = item.get("file_path") if isinstance(item, dict) else None
                        if not path or path in read_paths or len(read_paths) >= 2:
                            continue
                        read_paths.add(path)
                        read_arguments = {"project_id": project_id, "file_path": path}
                        read_record = {"tool": "repo_read_file", "arguments": read_arguments, "reason": "Inspect a file returned by repository search."}
                        try:
                            read_result = await self.gateway.call("repo_read_file", read_arguments)
                            read_record.update({"status": "success", "summary": self._summarize(read_result)})
                        except Exception as exc:
                            read_record.update({"status": "error", "error": str(exc)})
                        trace.append(read_record)
            except Exception as exc:
                logger.warning("mcp_tool_call_failed", tool=call.name, error=str(exc))
                record.update({"status": "error", "error": str(exc)})
                trace.append(record)
        return trace

    def select_execution_tools(
        self,
        *,
        project_id: str,
        query: str,
        user_confirmed: bool = False,
    ) -> list[ToolCall]:
        """Select a safe execution tool only after an explicit user confirmation.

        This method is intentionally separate from ``select_tools``. Repository
        questions must never become command execution merely because they mention
        tests or linting. The UI does not call this method yet.
        """
        if not user_confirmed:
            return []
        lower = query.lower()
        if any(phrase in lower for phrase in ("run tests", "run the tests", "execute tests", "execute the tests")):
            return [ToolCall("run_tests", {"project_id": project_id, "test_framework": "pytest"}, "Run the allowlisted pytest suite after user confirmation.")]
        if any(phrase in lower for phrase in ("run linter", "run the linter", "run ruff", "lint the repository")):
            return [ToolCall("run_linter", {"project_id": project_id, "linter": "ruff"}, "Run the allowlisted Ruff linter after user confirmation.")]
        return []

    @staticmethod
    def _search_terms(query: str) -> str:
        stop_words = {"why", "is", "the", "a", "an", "failing", "fails", "error", "please", "where", "what", "how", "does"}
        terms = [term.strip("?.,:;!()[]{}\"'") for term in query.lower().split()]
        return " ".join(term for term in terms if term and term not in stop_words) or query

    @staticmethod
    def _candidate_symbol(search_query: str) -> str:
        return search_query.split()[0] if search_query.split() else search_query

    @staticmethod
    def _summarize(result: Any) -> dict[str, Any]:
        if not isinstance(result, dict):
            return {"result_type": type(result).__name__}
        return {
            "keys": sorted(result.keys()),
            "total_found": result.get("total_found", result.get("total_symbols", result.get("total_dependencies"))),
            "file_path": result.get("file_path"),
        }
