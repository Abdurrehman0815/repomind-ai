"""Phase 26: lightweight deterministic evaluation for RepoMind outputs."""
from __future__ import annotations
from typing import Any

class EvaluationService:
    @staticmethod
    def evaluate(answer: str, citations: list[dict[str, Any]], case: dict[str, Any]) -> dict[str, Any]:
        lower = answer.lower()
        terms = case.get("required_terms", [])
        expected = set(case.get("expected_files", []))
        cited = {item.get("file_path") for item in citations}
        return {
            "case_id": case["id"],
            "term_recall": sum(term.lower() in lower for term in terms) / max(len(terms), 1),
            "citation_recall": len(expected & cited) / max(len(expected), 1),
            "passed": all(term.lower() in lower for term in terms) and expected.issubset(cited),
        }
