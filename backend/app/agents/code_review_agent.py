"""Phase 20: evidence-based review of a pasted or repository Git diff."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

import structlog

from app.agents.tool_using_agent import FastMCPToolGateway, ToolGateway

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class DiffLine:
    file_path: str
    line_number: int
    content: str


class CodeReviewAgent:
    """Review diffs with transparent rules and optional MCP repository context."""

    def __init__(self, session: Any = None, gateway: ToolGateway | None = None) -> None:
        self.session = session
        self.gateway = gateway or FastMCPToolGateway()

    async def review(
        self,
        *,
        project_id: str,
        session_id: str,
        pasted_diff: str | None = None,
    ) -> dict[str, Any]:
        """Analyse a diff and return source-grounded, deterministic findings."""
        trace: list[dict[str, Any]] = []
        diff = pasted_diff.strip() if pasted_diff else ""
        if not diff:
            diff, record = await self._call("git_diff", {"project_id": project_id}, "Retrieve the working-tree diff to review.")
            trace.append(record)
            if not isinstance(diff, dict) or diff.get("status") != "success":
                return self._error_result("I could not retrieve a Git diff to review.", trace)
            diff = str(diff.get("stdout", ""))

        changed_files, additions = self._parse_unified_diff(diff)
        # Context gathering is bounded and non-fatal: static review remains useful
        # for a pasted diff or an unindexed project.
        for file_path in changed_files[:5]:
            _, record = await self._call(
                "repo_read_file",
                {"project_id": project_id, "file_path": file_path},
                "Inspect the current version of a changed file.",
            )
            trace.append(record)
        if changed_files:
            _, record = await self._call(
                "repo_get_dependencies",
                {"project_id": project_id, "limit": 50},
                "Check dependency relationships around changed code.",
            )
            trace.append(record)
            test_query = f"test {PurePosixPath(changed_files[0]).stem}"
            _, record = await self._call(
                "repo_search",
                {"project_id": project_id, "query": test_query, "limit": 5},
                "Look for tests related to the first changed file.",
            )
            trace.append(record)

        findings = self._find_issues(additions)
        answer = self._format_answer(changed_files, findings)
        return {
            "answer": answer,
            "confidence": "high" if findings else "medium",
            "sources": [],
            "analysis_type": "code_review",
            "findings": findings,
            "metadata": {
                "changed_files": changed_files,
                "changed_files_count": len(changed_files),
                "findings_count": len(findings),
                "tool_trace": trace,
                "session_id": session_id,
            },
        }

    async def _call(self, tool: str, arguments: dict[str, Any], reason: str) -> tuple[Any, dict[str, Any]]:
        record: dict[str, Any] = {"tool": tool, "arguments": arguments, "reason": reason}
        try:
            result = await self.gateway.call(tool, arguments)
            record["status"] = "success"
            return result, record
        except Exception as exc:
            logger.warning("code_review_tool_failed", tool=tool, error=str(exc))
            record.update({"status": "error", "error": str(exc)})
            return None, record

    @staticmethod
    def _parse_unified_diff(diff: str) -> tuple[list[str], list[DiffLine]]:
        files: list[str] = []
        additions: list[DiffLine] = []
        current_file: str | None = None
        new_line = 0
        hunk_pattern = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")

        for raw_line in diff.splitlines():
            if raw_line.startswith("+++ "):
                candidate = raw_line[4:].strip()
                current_file = None if candidate == "/dev/null" else candidate.removeprefix("b/")
                if current_file and current_file not in files:
                    files.append(current_file)
                continue
            hunk = hunk_pattern.match(raw_line)
            if hunk:
                new_line = int(hunk.group(1))
                continue
            if not current_file or raw_line.startswith(("diff --git", "index ", "--- ")):
                continue
            if raw_line.startswith("+"):
                additions.append(DiffLine(current_file, new_line, raw_line[1:]))
                new_line += 1
            elif raw_line.startswith("-"):
                continue
            else:
                new_line += 1
        return files, additions

    @staticmethod
    def _find_issues(additions: list[DiffLine]) -> list[dict[str, Any]]:
        findings: list[dict[str, Any]] = []
        secret = re.compile(r"(?i)\b(api[_-]?key|password|secret|access[_-]?token)\s*=\s*[\"'][^\"']{4,}[\"']")
        for line in additions:
            text = line.content.strip()
            if secret.search(text):
                findings.append(CodeReviewAgent._finding("high", "hardcoded-secret", line, "A credential-like value is added to source code. Move it to a secret store or environment configuration."))
            elif "verify=False" in text:
                findings.append(CodeReviewAgent._finding("high", "tls-verification-disabled", line, "TLS certificate verification is disabled, allowing man-in-the-middle attacks."))
            elif re.search(r"\b(eval|exec)\s*\(", text):
                findings.append(CodeReviewAgent._finding("high", "dynamic-code-execution", line, "Dynamic code execution is introduced; validate whether untrusted input can reach it."))
            elif re.match(r"except\s+(Exception|BaseException)\s*:", text):
                findings.append(CodeReviewAgent._finding("medium", "broad-exception", line, "A broad exception handler can hide unexpected failures; catch expected exception types and log context."))
            elif text == "pass" and findings and findings[-1]["file_path"] == line.file_path:
                findings.append(CodeReviewAgent._finding("medium", "swallowed-exception", line, "This added no-op can silently suppress a preceding failure."))
            elif re.match(r"print\(", text):
                findings.append(CodeReviewAgent._finding("low", "debug-output", line, "Debug output was added to application code; use structured logging or remove it before release."))
        severity_order = {"high": 0, "medium": 1, "low": 2}
        return sorted(findings, key=lambda item: (severity_order[item["severity"]], item["file_path"], item["line"]))

    @staticmethod
    def _finding(severity: str, rule: str, line: DiffLine, message: str) -> dict[str, Any]:
        return {"severity": severity, "rule": rule, "file_path": line.file_path, "line": line.line_number, "evidence": line.content, "message": message}

    @staticmethod
    def _format_answer(files: list[str], findings: list[dict[str, Any]]) -> str:
        if not files:
            return "No changed files were found in the supplied diff."
        if not findings:
            return f"Reviewed {len(files)} changed file(s). No rule-based issues were found; this is not a guarantee that the change is defect-free."
        lines = [f"Reviewed {len(files)} changed file(s) and found {len(findings)} issue(s):"]
        lines.extend(f"- [{item['severity'].upper()}] {item['file_path']}:{item['line']} — {item['message']}" for item in findings)
        return "\n".join(lines)

    @staticmethod
    def _error_result(message: str, trace: list[dict[str, Any]]) -> dict[str, Any]:
        return {"answer": message, "confidence": "low", "sources": [], "analysis_type": "code_review", "findings": [], "metadata": {"tool_trace": trace}}
