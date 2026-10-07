# RepoMind AI — Evaluation Framework

## Overview

The evaluation framework measures the quality of RepoMind AI across
all major functional areas. It is designed to be run after every major change
and produces both machine-readable JSON and a human-readable console report.

---

## Evaluation CLI

```bash
python -m evals.run
```

Options:
```
python -m evals.run --category retrieval
python -m evals.run --category citations
python -m evals.run --category routing
python -m evals.run --category tools
python -m evals.run --category review
python -m evals.run --category planning
python -m evals.run --report-path reports/latest.json
```

---

## Evaluation Categories

### 1. Retrieval Quality

**Dataset:** `evals/datasets/retrieval_cases.jsonl`

```json
{
  "id": "ret-001",
  "query": "Where is JWT validation implemented?",
  "expected_files": ["backend/auth/service.py", "backend/middleware/auth.py"],
  "top_k": 5
}
```

**Metrics:**
- Recall@5: fraction of expected files in top-5 results
- Recall@10
- MRR (Mean Reciprocal Rank)
- Average position of first expected result

---

### 2. Citation Accuracy

**Dataset:** `evals/datasets/qa_cases.jsonl`

```json
{
  "id": "qa-001",
  "question": "Where is authentication implemented?",
  "expected_citations": [
    {"file": "backend/auth/service.py", "min_line": 1, "max_line": 200},
    {"file": "backend/auth/router.py", "min_line": 1, "max_line": 100}
  ]
}
```

**Metrics:**
- Citation precision: fraction of returned citations that are valid
- Citation recall: fraction of expected citations that are returned
- Stale citation rate: citations pointing to changed files
- Invented citation rate: citations pointing to non-existent files

---

### 3. Intent Routing

**Dataset:** Inline in `evals/runners/routing_eval.py`

**Metrics:**
- Routing accuracy per intent category
- Macro F1 across all categories
- Confusion matrix

---

### 4. Answer Groundedness

**Dataset:** `evals/datasets/qa_cases.jsonl`

**Metric:** LLM-as-judge groundedness score (0–1)

Each answer is evaluated for:
- Does it cite evidence from the retrieved context?
- Does it avoid inventing files or functions?
- Does it say "I could not find" when evidence is absent?

---

### 5. Tool Selection

**Dataset:** `evals/datasets/tool_cases.jsonl`

```json
{
  "id": "tool-001",
  "query": "Show me the git status",
  "expected_tool": "git_status",
  "should_require_approval": false
}
```

**Metrics:**
- Tool selection accuracy
- False positive rate (tool called when not needed)
- False negative rate (tool not called when needed)
- Safety compliance (dangerous tools blocked)

---

### 6. Code Review Quality

**Dataset:** `evals/datasets/review_cases.jsonl`

```json
{
  "id": "rev-001",
  "diff": "...",
  "expected_findings": [
    {"title": "SQL injection risk", "severity": "CRITICAL", "file": "backend/db.py"}
  ]
}
```

**Metrics:**
- Finding precision: true findings / total findings
- Finding recall: found expected / total expected
- Severity calibration: correct severity assignment

---

## Sample Repository

The evaluation uses a dedicated sample repository:

```
evals/sample-repo/
    backend/
        auth/
            router.py      # JWT validation, login endpoint
            service.py     # AuthService, token creation
            models.py      # User model
        payments/
            service.py     # PaymentService, Stripe integration
            router.py
        database.py        # SQLAlchemy setup
    frontend/
        src/
            auth/          # Login form, auth context
            checkout/      # Checkout flow
    tests/
        test_auth.py
        test_payments.py
    README.md
```

This sample repository includes:
- 20 code navigation Q&A pairs
- 10 architecture explanation Q&A pairs
- 10 change impact Q&A pairs
- 10 test plan Q&A pairs
- 10 diff-review examples with known findings

---

## Report Format

Console output:
```
RepoMind AI Evaluation Report
==============================
Run ID:          eval-20261007-143022
Project:         sample-repo
LLM Provider:    ollama/llama3.2
Embedding:       nomic-embed-text

Category          Cases    Passed    Failed    Score
──────────────────────────────────────────────────
Retrieval         30       27        3         0.90
Citations         20       17        3         0.85
Routing           15       15        0         1.00
Groundedness      20       16        4         0.80
Tool Selection    10        9        1         0.90
Code Review       10        7        3         0.70
──────────────────────────────────────────────────
TOTAL             105      91        14        0.87

Average Latency:  1.4s
```

JSON output:
```json
{
  "run_id": "eval-20261007-143022",
  "timestamp": "2026-10-07T14:30:22Z",
  "provider": "ollama",
  "model": "llama3.2",
  "categories": { ... },
  "overall_score": 0.87,
  "avg_latency_ms": 1400
}
```

---

## Baseline Targets

After Phase 26 (first evaluation run), the following baselines should be met:

| Metric | Minimum Target |
|---|---|
| Retrieval Recall@5 | 0.80 |
| Citation Precision | 0.85 |
| Routing Accuracy | 0.90 |
| Groundedness | 0.75 |
| Tool Selection | 0.85 |
| End-to-End Pass Rate | 0.80 |

If any metric is below target, the issue must be diagnosed before the next phase.
