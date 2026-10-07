# RepoMind AI

> An agentic codebase intelligence copilot that understands software repositories,
> answers questions with source citations, analyzes architecture and dependencies,
> creates implementation plans, reviews code changes, generates test plans,
> and safely executes developer tools.

---

## What is RepoMind AI?

RepoMind AI is a developer intelligence platform — not a chatbot. It combines:

- **Code-aware RAG** — retrieval grounded in real source code, not PDFs
- **Agentic orchestration** — LangGraph-based supervisor + specialist agents
- **Source citations** — every answer cites exact file paths and line numbers
- **Dependency graph** — visual map of module relationships
- **Safe tool execution** — controlled subprocess with strict allowlists
- **MCP server** — interoperable tool exposure via the Model Context Protocol
- **Evaluation framework** — measurable retrieval, citation, and answer quality
- **Provider abstraction** — works with local Ollama; Bedrock added last

---

## Features

| Feature | Description |
|---|---|
| Repository Import | Select and register any local Git repository |
| Incremental Indexing | Only re-process changed files on re-index |
| Code Parsing | Tree-sitter / AST symbol and import extraction |
| Embedding Pipeline | Local embedding model via configurable provider |
| Hybrid Search | Vector + keyword search with rank fusion |
| Reranking | Optional reranker for top-k context selection |
| Grounded Chat | Natural-language Q&A with source evidence |
| Citations | File:line citations validated against stored chunks |
| Architecture Explanation | Trace execution paths through the codebase |
| Change Impact | Predict affected files from dependency graph |
| Implementation Plans | Evidence-based step-by-step change plans |
| Code Review | Diff analysis with severity-ranked findings |
| Test Plan Generation | Unit/integration/API/edge/security test plans |
| Debugging Workflow | Trace errors through route → service → DB |
| Safe Tool Execution | git, pytest, ruff, mypy — no arbitrary shell |
| MCP Server | Controlled tool exposure via MCP protocol |
| Agent Memory | Session + project-level memory persistence |
| Agent Trace UI | Step-by-step execution timeline |
| Feedback System | Thumbs-up/down with categorized reasons |
| Evaluation CLI | `python -m evals.run` with metrics report |
| Observability | Structured logging, request IDs, latency tracking |
| Security | Path isolation, secret exclusion, injection defense |

---

## Architecture

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full architecture document with Mermaid diagrams.

```
Frontend (React/Vite/TypeScript)
        ↓ REST + SSE
Backend (FastAPI/Python)
        ↓
  ┌─────┴──────────┐
  Agent Layer       Tool Layer
  (LangGraph)       (MCP Server)
        ↓                ↓
  ┌─────┴──────┐    Service Layer
  RAG Pipeline  │
  │   Vector DB │
  │   Full-text │
  └─────────────┘
        ↓
  PostgreSQL + pgvector
```

---

## Technology Stack

### Frontend
- React 18 + TypeScript
- Vite
- Tailwind CSS
- shadcn/ui
- TanStack Query
- React Router

### Backend
- Python 3.11+
- FastAPI
- Pydantic v2
- SQLAlchemy 2.x
- Alembic

### Database
- PostgreSQL 15+
- pgvector extension

### AI / ML
- Ollama (local LLM inference)
- Local embedding model
- LangChain (components only)
- LangGraph (agent orchestration)

### Code Intelligence
- Tree-sitter (multi-language parsing)
- Python AST (Python-specific)
- Import/dependency extraction
- Symbol extraction

### Infrastructure
- Docker + Docker Compose
- GitHub Actions (CI)

### Future (Phase 32+)
- Amazon Bedrock (Converse API)
- Optional: S3, RDS, CloudWatch, AgentCore

---

## Local Setup

### Prerequisites

- Docker and Docker Compose
- Node.js 20+
- Python 3.11+
- [Ollama](https://ollama.ai) installed locally

### 1. Clone and configure

```bash
git clone <repo>
cd repomind-ai
cp .env.example .env
# Edit .env with your settings
```

### 2. Start services

```bash
docker compose up -d
```

### 3. Install backend dependencies

```bash
cd backend
pip install -r requirements.txt
alembic upgrade head
```

### 4. Install frontend dependencies

```bash
cd frontend
npm install
npm run dev
```

### 5. Verify startup

```bash
curl http://localhost:8000/health
```

---

## Ollama Setup

```bash
# Install Ollama: https://ollama.ai
ollama pull <your-configured-model>
ollama pull nomic-embed-text   # default embedding model
```

Configure in `.env`:

```env
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2
EMBEDDING_PROVIDER=local
EMBEDDING_MODEL=nomic-embed-text
```

---

## Database Setup

PostgreSQL with pgvector is provided via Docker Compose.

```bash
docker compose up postgres -d
cd backend
alembic upgrade head
```

---

## Indexing Workflow

1. Open the RepoMind UI
2. Navigate to **Projects → New Project**
3. Enter the path to your local repository
4. Click **Index Repository**
5. Monitor progress: files scanned, symbols extracted, embeddings generated

Incremental re-index only processes changed files.

---

## Agent Architecture

```
SupervisorAgent
    ├── CodebaseAnalystAgent
    ├── PlannerAgent
    ├── CodeReviewAgent
    ├── TestAgent
    └── ToolExecutionAgent
```

Each agent uses LangGraph state machines with explicit nodes.
See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

---

## MCP Architecture

The RepoMind MCP server exposes controlled tools:

```
repo_list_files     repo_read_file      repo_search
repo_get_symbols    repo_get_dependencies
git_status          git_diff            git_log
run_tests           run_linter
```

MCP tools call the same internal service layer used by the backend.
No business logic is duplicated inside MCP.

---

## Security Model

- Repository paths validated and isolated per project
- Sensitive files excluded from indexing (.env, *.key, *.pem, credentials)
- LLM never given unrestricted shell access
- Tool execution via strict allowlist — no `shell=True`
- Repository content treated as untrusted data (prompt injection defense)
- Secrets never logged or sent to LLM
- Cross-project data isolation enforced

See [docs/SECURITY.md](docs/SECURITY.md).

---

## Testing

```bash
# Backend unit + integration tests
cd backend
pytest tests/ -v

# Frontend tests
cd frontend
npm test

# End-to-end tests
pytest tests/e2e/ -v

# Security tests
pytest tests/security/ -v
```

---

## Evaluation

```bash
python -m evals.run
```

Output:
```
Total cases:        120
Passed:             112
Failed:               8
Retrieval recall:   0.91
Citation accuracy:  0.88
Tool selection:     0.94
Average latency:    1.2s
```

See [docs/EVALUATION.md](docs/EVALUATION.md).

---

## AWS Bedrock Integration

> ⚠️ Bedrock is implemented in the **final phase only**, after all local phases pass.

To switch to Bedrock:

```env
LLM_PROVIDER=bedrock
AWS_REGION=us-east-1
BEDROCK_MODEL_ID=anthropic.claude-3-5-sonnet-20241022-v2:0
```

No code changes required. The provider abstraction handles routing.

---

## Future Deployment

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for production deployment options.

---

## Implementation Status

See [docs/IMPLEMENTATION_STATUS.md](docs/IMPLEMENTATION_STATUS.md) for the current phase checklist.
