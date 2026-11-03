"""
RepoMind AI — Evaluation runner

Runs the grounding cases in ``evals/phase26_cases.json`` against a running
RepoMind stack:

1. uploads ``evals/sample-repo`` through the folder-upload API,
2. waits for indexing to finish,
3. asks every case's question and scores the answer:
   - citation recall: share of ``expected_files`` present in the citations
   - term recall:     share of ``required_terms`` present in the answer text
4. writes a JSON report to ``evals/reports/`` and deletes the eval project.

Usage (stack running, e.g. ``docker compose up -d``):
    python -m evals.run [--api http://localhost:8000]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from pathlib import Path

import httpx

EVALS_DIR = Path(__file__).resolve().parent
SAMPLE_REPO = EVALS_DIR / "sample-repo"
CASES_FILE = EVALS_DIR / "phase26_cases.json"
REPORTS_DIR = EVALS_DIR / "reports"
PASS_THRESHOLD = 1.0  # every expected file cited and every term present


def upload_sample_repo(client: httpx.Client) -> str:
    files = [
        ("files", (f"sample-repo/{path.relative_to(SAMPLE_REPO).as_posix()}", path.read_bytes()))
        for path in sorted(SAMPLE_REPO.rglob("*"))
        if path.is_file()
    ]
    resp = client.post("/api/v1/projects/upload", files=files, data={"name": "evals-sample-repo"})
    resp.raise_for_status()
    return resp.json()["id"]


def wait_until_indexed(client: httpx.Client, project_id: str, timeout_s: int = 300) -> float:
    started = time.time()
    while time.time() - started < timeout_s:
        status = client.get(f"/api/v1/projects/{project_id}").json()["status"]
        if status == "indexed":
            return time.time() - started
        if status == "error":
            raise RuntimeError("Indexing the sample repository failed; check `docker compose logs backend`.")
        time.sleep(2)
    raise TimeoutError("Indexing did not finish in time.")


def score_case(client: httpx.Client, project_id: str, case: dict) -> dict:
    started = time.time()
    resp = client.post(
        "/api/v1/chat",
        params={"project_id": project_id, "session_id": str(uuid.uuid4()), "message": case["query"], "stream": False},
    )
    resp.raise_for_status()
    data = resp.json()
    answer = data.get("response", "")
    cited = {citation["file_path"] for citation in data.get("citations", [])}
    expected = case.get("expected_files", [])
    terms = case.get("required_terms", [])
    citation_recall = sum(path in cited for path in expected) / len(expected) if expected else 1.0
    term_recall = sum(term.lower() in answer.lower() for term in terms) / len(terms) if terms else 1.0
    return {
        "id": case["id"],
        "query": case["query"],
        "intent": data.get("intent"),
        "latency_s": round(time.time() - started, 2),
        "citation_recall": citation_recall,
        "term_recall": term_recall,
        "passed": citation_recall >= PASS_THRESHOLD and term_recall >= PASS_THRESHOLD,
        "cited_files": sorted(cited),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--api", default="http://localhost:8000", help="RepoMind backend URL")
    args = parser.parse_args()

    cases = json.loads(CASES_FILE.read_text(encoding="utf-8"))
    with httpx.Client(base_url=args.api, timeout=180) as client:
        project_id = upload_sample_repo(client)
        try:
            index_s = wait_until_indexed(client, project_id)
            results = [score_case(client, project_id, case) for case in cases]
        finally:
            client.delete(f"/api/v1/projects/{project_id}")

    passed = sum(result["passed"] for result in results)
    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "indexing_s": round(index_s, 2),
        "passed": passed,
        "total": len(results),
        "results": results,
    }
    REPORTS_DIR.mkdir(exist_ok=True)
    report_path = REPORTS_DIR / f"eval-{time.strftime('%Y%m%d-%H%M%S')}.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"Indexed sample repo in {report['indexing_s']}s")
    for result in results:
        mark = "PASS" if result["passed"] else "FAIL"
        print(f"[{mark}] {result['id']}: citations {result['citation_recall']:.0%}, terms {result['term_recall']:.0%}, {result['latency_s']}s")
    print(f"{passed}/{len(results)} passed — report: {report_path}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
