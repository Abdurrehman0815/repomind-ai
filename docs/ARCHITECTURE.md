# RepoMind AI — Architecture

## Overview

RepoMind AI is built as a layered, modular system with clear separation between
the frontend, API gateway, agent layer, retrieval pipeline, and data stores.

---

## High-Level Architecture

```mermaid
graph TB
    subgraph Frontend["Frontend (React/Vite/TypeScript)"]
        UI[Chat UI]
        SV[Source Viewer]
        DG[Dependency Graph]
        AT[Agent Trace]
        EV[Evaluations]
    end

    subgraph Backend["Backend (FastAPI/Python)"]
        API[REST API + SSE]
        AUTH[Auth Middleware]
        OBS[Observability]
    end

    subgraph AgentLayer["Agent Layer (LangGraph)"]
        SUP[SupervisorAgent]
        CA[CodebaseAnalystAgent]
        PL[PlannerAgent]
        CR[CodeReviewAgent]
        TA[TestAgent]
        TE[ToolExecutionAgent]
    end

    subgraph MCPServer["MCP Server (FastMCP)"]
        MCP[RepoMind MCP]
        MT[MCP Tools]
    end

    subgraph Services["Service Layer"]
        IS[Indexing Service]
        RS[Retrieval Service]
        CS[Citation Service]
        DS[Dependency Service]
        TS[Tool Service]
        MS[Memory Service]
    end

    subgraph DataLayer["Data Layer"]
        PG[(PostgreSQL)]
        VEC[(pgvector)]
        FS[File System]
    end

    subgraph AIProviders["AI Providers"]
        AZ[Azure AI Foundry - gpt-4.1-mini]
        AZE[Azure AI Foundry - text-embedding-3-small]
        OL[Ollama Local - offline fallback]
    end

    Frontend --> API
    API --> AUTH
    API --> AgentLayer
    AgentLayer --> Services
    AgentLayer --> MCPServer
    MCPServer --> Services
    Services --> DataLayer
    Services --> AIProviders
```

---

## Repository Ingestion Pipeline

```mermaid
flowchart LR
    A[User selects repo path] --> B[Validate path]
    B --> C[Create repository record]
    C --> D[Detect Git / commit hash]
    D --> E[Walk file tree]
    E --> F[Apply ignore rules]
    F --> G[Hash files]
    G --> H[Detect language]
    H --> I[Parse AST / Tree-sitter]
    I --> J[Extract symbols]
    J --> K[Extract imports]
    K --> L[Create chunks with metadata]
    L --> M[Generate embeddings]
    M --> N[Store vectors + chunks]
    N --> O[Build dependency graph]
    O --> P[Mark indexing complete]
```

---

## Hybrid Retrieval Pipeline

```mermaid
flowchart TD
    Q[User Query] --> QN[Query Normalization]
    QN --> QR[Optional Query Rewrite]
    QR --> VR[Vector Search - pgvector cosine]
    QR --> KR[Keyword Search - PostgreSQL FTS]
    VR --> RF[Rank Fusion - RRF]
    KR --> RF
    RF --> DD[Deduplication]
    DD --> RR[Optional Reranker]
    RR --> CS[Context Selection - top 5-8]
    CS --> LLM[LLM Generation]
```

---

## Agent Orchestration (LangGraph)

```mermaid
flowchart TD
    START --> CI[classify_intent]
    CI --> SW{Intent Router}
    SW --> |navigation / architecture| CA[CodebaseAnalystAgent]
    SW --> |change_impact / plan| PL[PlannerAgent]
    SW --> |diff_review| CR[CodeReviewAgent]
    SW --> |test_plan| TA[TestAgent]
    SW --> |debugging| CA
    SW --> |tool_action| TE[ToolExecutionAgent]
    CA --> VA[validate_answer]
    PL --> VA
    CR --> VA
    TA --> VA
    TE --> VA
    VA --> GC[generate_citations]
    GC --> END
```

---

## Multi-Agent Responsibilities

| Agent | Responsibilities |
|---|---|
| SupervisorAgent | Intent classification, routing, final validation |
| CodebaseAnalystAgent | Code retrieval, symbol analysis, architecture explanation |
| PlannerAgent | Change impact, implementation planning |
| CodeReviewAgent | Diff parsing, finding generation, severity ranking |
| TestAgent | Test strategy, unit/integration/edge/security test plans |
| ToolExecutionAgent | Controlled tool invocation, result interpretation |

---

## Directory Structure

```
repomind-ai/
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   ├── pages/
│   │   ├── hooks/
│   │   ├── services/
│   │   └── types/
│   ├── tests/
│   ├── index.html
│   ├── vite.config.ts
│   └── package.json
│
├── backend/
│   ├── app/
│   │   ├── api/           # FastAPI routers
│   │   ├── core/          # Config, startup, DI
│   │   ├── db/            # SQLAlchemy engine, session
│   │   ├── models/        # SQLAlchemy ORM models
│   │   ├── schemas/       # Pydantic request/response schemas
│   │   ├── services/      # Business logic
│   │   ├── repositories/  # Data access layer
│   │   ├── ingestion/     # File scanning, parsing, chunking
│   │   ├── retrieval/     # Hybrid search, reranking
│   │   ├── agents/        # LangGraph agents + nodes
│   │   ├── tools/         # Tool implementations
│   │   ├── security/      # Path validation, allowlists
│   │   ├── ai/
│   │   │   └── providers/ # LLMProvider abstraction
│   │   └── observability/ # Logging, tracing, metrics
│   ├── tests/
│   │   ├── unit/
│   │   ├── integration/
│   │   ├── e2e/
│   │   └── security/
│   ├── alembic/
│   ├── alembic.ini
│   └── requirements.txt
│
├── mcp-server/
│   ├── app/
│   │   ├── server.py
│   │   └── tools/
│   └── tests/
│
├── evals/
│   ├── datasets/
│   │   ├── qa_cases.jsonl
│   │   ├── retrieval_cases.jsonl
│   │   ├── tool_cases.jsonl
│   │   └── review_cases.jsonl
│   ├── runners/
│   └── reports/
│
├── docs/
├── scripts/
├── docker-compose.yml
├── .env.example
├── .gitignore
└── README.md
```

---

## Data Model Overview

```mermaid
erDiagram
    users ||--o{ projects : owns
    projects ||--o{ repositories : contains
    repositories ||--o{ repository_snapshots : has
    repositories ||--o{ files : contains
    files ||--o{ symbols : defines
    files ||--o{ code_chunks : chunked_into
    code_chunks ||--o{ embeddings : has
    files ||--o{ dependencies : imports
    projects ||--o{ sessions : has
    sessions ||--o{ messages : contains
    sessions ||--o{ agent_runs : triggers
    agent_runs ||--o{ agent_steps : contains
    agent_runs ||--o{ tool_runs : executes
    messages ||--o{ citations : references
    messages ||--o{ feedback : receives
```

---

## LLM Provider Abstraction

```
LLMProvider (abstract)
    ├── generate(prompt, options) → str
    ├── stream(prompt, options) → AsyncIterator[str]
    ├── structured_generate(prompt, schema, options) → BaseModel
    └── tool_calling(prompt, tools, options) → ToolCallResult

AzureFoundryProvider  (default: Azure AI Foundry, OpenAI or Anthropic wire format)
LocalOllamaProvider   (offline fallback)

EmbeddingProvider: AzureEmbeddingProvider | OllamaEmbeddingProvider | LocalEmbeddingProvider
```

The application code always calls `get_llm_provider()` — never Azure or Ollama directly.

---

## Security Architecture

See [SECURITY.md](SECURITY.md) for full details.

Key controls:
1. **Path isolation** — every repository access validates against project root
2. **Secret exclusion** — .env, *.key, *.pem excluded from indexing
3. **Prompt injection defense** — repository content never promoted to system instructions
4. **Tool allowlist** — only pre-approved commands can be executed
5. **Human-in-the-loop** — file modifications require explicit user approval

---

## Observability

Every request carries:

```
request_id → session_id → agent_run_id → node_name
```

LLM calls track:
- model provider + model name
- input/output tokens (when available)
- latency_ms
- estimated cost (zero for local, real for Azure)
