"""Phase 20 benchmark: intentionally buggy diffs yield meaningful findings."""
from __future__ import annotations

import pytest

from app.agents.code_review_agent import CodeReviewAgent


class FakeGateway:
    def __init__(self, diff: str = "") -> None:
        self.diff = diff
        self.calls: list[str] = []

    async def call(self, tool_name: str, arguments: dict):
        self.calls.append(tool_name)
        if tool_name == "git_diff":
            return {"status": "success", "stdout": self.diff}
        return {"status": "success", "results": []}


@pytest.mark.asyncio
async def test_detects_hardcoded_secret_in_buggy_diff():
    diff = """diff --git a/app/config.py b/app/config.py
--- a/app/config.py
+++ b/app/config.py
@@ -1,1 +1,2 @@
 settings = {}
+API_KEY = \"live-secret-value\"
"""
    result = await CodeReviewAgent(gateway=FakeGateway()).review(project_id="p1", session_id="s1", pasted_diff=diff)
    assert result["findings"][0]["rule"] == "hardcoded-secret"
    assert result["findings"][0]["file_path"] == "app/config.py"


@pytest.mark.asyncio
async def test_detects_swallowed_broad_exception_in_buggy_diff():
    diff = """diff --git a/app/service.py b/app/service.py
--- a/app/service.py
+++ b/app/service.py
@@ -4,1 +4,3 @@
 def load():
+    except Exception:
+        pass
"""
    result = await CodeReviewAgent(gateway=FakeGateway()).review(project_id="p1", session_id="s1", pasted_diff=diff)
    assert {item["rule"] for item in result["findings"]} == {"broad-exception", "swallowed-exception"}


@pytest.mark.asyncio
async def test_clean_diff_does_not_create_speculative_finding():
    diff = """diff --git a/app/maths.py b/app/maths.py
--- a/app/maths.py
+++ b/app/maths.py
@@ -1,1 +1,2 @@
 def add(a, b):
+    return a + b
"""
    result = await CodeReviewAgent(gateway=FakeGateway()).review(project_id="p1", session_id="s1", pasted_diff=diff)
    assert result["findings"] == []
    assert "No rule-based issues" in result["answer"]


@pytest.mark.asyncio
async def test_uses_git_diff_and_context_tools_when_diff_not_pasted():
    diff = """diff --git a/src/auth.py b/src/auth.py
--- a/src/auth.py
+++ b/src/auth.py
@@ -1,1 +1,2 @@
 def login():
+    print(\"debug\")
"""
    gateway = FakeGateway(diff)
    result = await CodeReviewAgent(gateway=gateway).review(project_id="p1", session_id="s1")
    assert {"git_diff", "repo_read_file", "repo_get_dependencies", "repo_search"}.issubset(gateway.calls)
    assert result["findings"][0]["rule"] == "debug-output"
