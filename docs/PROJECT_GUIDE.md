# RepoMind AI: Project Guide

A plain-language walkthrough of how RepoMind works, how to set it up, what every command does, and how Docker lets you move it to another laptop. Read it top to bottom once, then use it as a reference.

---

## Contents
1. [What RepoMind is](#1-what-repomind-is)
2. [The big picture](#2-the-big-picture)
3. [What happens when you import a repository](#3-what-happens-when-you-import-a-repository)
4. [What happens when you ask a question](#4-what-happens-when-you-ask-a-question)
5. [Azure AI Foundry setup](#5-azure-ai-foundry-setup)
6. [What runs locally and what runs on Azure](#6-what-runs-locally-and-what-runs-on-azure)
7. [Installation: every command, and why](#7-installation-every-command-and-why)
8. [Docker explained](#8-docker-explained)
9. [Moving the project to another laptop](#9-moving-the-project-to-another-laptop)
10. [Everyday command cheat sheet](#10-everyday-command-cheat-sheet)
11. [Troubleshooting](#11-troubleshooting)
12. [Where things live in the code](#12-where-things-live-in-the-code)
13. [Glossary](#13-glossary)

---

## 1. What RepoMind is

RepoMind is a **chat assistant for a codebase**. You give it a repository, and you can then ask "where is X?", "how does Y work?", "what breaks if I change Z?", "write me a test plan" and so on.

The key idea is **grounding**. The AI model doesn't answer from memory. RepoMind first **finds the relevant pieces of your code**, then gives *only those pieces* to the model and asks it to answer from them, citing `file:line`. That's why the answers are specific to your project and come with sources.

This technique is called **RAG (Retrieval-Augmented Generation)**:
**R**etrieve the right code → **A**ugment the prompt with it → **G**enerate the answer.

---

## 2. The big picture

```
 You (browser, http://localhost:3000)
        │
        ▼
 ┌──────────────┐   REST API   ┌──────────────────────────────────────────┐
 │  FRONTEND    │ ───────────▶ │  BACKEND (FastAPI, Python)               │
 │  React app   │              │                                          │
 │  in Nginx    │ ◀─────────── │  • Ingestion: scan → parse → chunk       │
 └──────────────┘   answers    │  • Retrieval: vector + keyword search    │
                               │  • Agents: supervisor + 7 specialists    │
                               │  • MCP tools: repo / git / tests         │
                               └───────┬──────────────────────┬───────────┘
                                       │                      │ HTTPS
                                       ▼                      ▼
                         ┌──────────────────────┐   ┌──────────────────────────┐
                         │ DATABASE             │   │ AZURE AI FOUNDRY (cloud) │
                         │ PostgreSQL + pgvector│   │ • text-embedding-3-small │
                         │ files, symbols,      │   │ • gpt-4.1-mini           │
                         │ chunks, vectors, chat│   └──────────────────────────┘
                         └──────────────────────┘
```

There are three parts on your laptop (frontend, backend, database), each in its own Docker container. Two AI models run in the cloud on Azure.

---

## 3. What happens when you import a repository

When you click **Import Repository** (GitHub URL or folder), the backend runs this pipeline in the background. The Projects page shows its progress.

| Step | What happens | Why | Code |
|---|---|---|---|
| 1. Get the code | A GitHub URL is cloned with `git clone --depth 1`. A chosen folder is uploaded and copied into the workspace. Your original files are never touched. | The backend needs its own copy to read | `ingestion/service.py`, `api/v1/projects.py` |
| 2. Scan | Walk every file, skip `node_modules`, `.git`, secrets and binaries, detect the language, compute a **hash** (fingerprint) of each file | The hash lets a re-import skip files that haven't changed | `ingestion/scanner.py` |
| 3. Read safely | Decode the text (handles UTF-16 files such as Windows `requirements.txt`) and strip invalid characters | PostgreSQL rejects NUL bytes, which caused the early "Error" status | `ingestion/text_io.py` |
| 4. Parse | Find functions, classes, methods and imports. Python uses the built-in `ast` module; JS/TS uses a dedicated parser | So answers can point at exact symbols, and the dependency graph can be built | `ingestion/parsers/`, `symbol_extractor.py` |
| 5. Chunk | Split each file into pieces of about 512 tokens, cut along function/class boundaries, with overlap | A model can't read a whole repo at once, so it gets the few chunks that matter | `ingestion/chunker.py` |
| 6. Embed | Send chunks to **Azure `text-embedding-3-small`**, which turns each one into 768 numbers (a vector) that capture its *meaning* | Lets the app find code by meaning ("upload handling") rather than exact words | `ai/providers/azure_embedding.py` |
| 7. Store | Save files, symbols, chunks and vectors in PostgreSQL + pgvector | So searching later is instant | `models/`, `repositories/` |

When every file is done, the status changes to **indexed**. Embedding is sent in batches of 64, with 6 batches in parallel. That's why a small repo takes seconds rather than minutes.

---

## 4. What happens when you ask a question

```
"Where is the transcribe function defined?"
   │
   ▼  1. Classify intent      → code_navigation   (supervisor_service.py)
   ▼  2. Embed the question   → Azure embeddings (question becomes a vector)
   ▼  3. Hybrid search        → vector similarity + keyword search, merged by rank
   ▼  4. Specialist agent     → Codebase Analyst finds symbols + exact lines
   ▼  5. Build prompt         → question + top code chunks labelled [app.py:L18-L31]
   ▼  6. Generate             → Azure gpt-4.1-mini writes the answer from that code only
   ▼  7. Citations            → built from stored line ranges, de-duplicated
   ▼
"`transcribe` is defined in app.py lines 18–31" + Sources: app.py:L16-17
```

**The agents (step 4).** The supervisor picks one specialist based on the question:

| Agent | Triggered by words like | Does |
|---|---|---|
| Codebase Analyst | explain, how, architecture, where, function, class | architecture explanations, code navigation |
| Change Impact | change, modify, add, remove, affected | follows the dependency graph to affected files |
| Planner | plan, implement, build, create | step-by-step implementation plan |
| Test Plan | test plan, testing strategy | six-category test plan from the real code |
| Debugging | debug, error, bug, issue | likely root cause, how to confirm, suggested fix |
| Code Review | review, diff, pull request | reviews the git working-tree diff |
| Tool-Using | (runs alongside) | calls MCP tools (search, read, git…) for extra evidence |

**Why answers are trustworthy.**
- The model only sees retrieved code, and is told to say "I could not find sufficient evidence" when the code doesn't cover the question.
- Citations come from the database line ranges, not from the model's text.
- Code is marked as *untrusted data*, so instructions hidden in a repo ("ignore your rules…") are not followed.

---

## 5. Azure AI Foundry setup

The steps below are the ones used for this project. Azure renames buttons often, so look for similar wording.

1. **Sign in** at https://portal.azure.com. You need a subscription with billing enabled.
2. **Create a resource group**: Resource groups → **Create** → name `repomind-rg` → region **East US 2** → Review + create.
3. **Create the Foundry resource**: search **Microsoft Foundry** → **Create** → resource group `repomind-rg`, same region, a name (e.g. `repomindai`) → Create.
4. **Open Foundry** (https://ai.azure.com), select the project, then go to **Models** → **Deploy a base model**:
   - `gpt-4.1-mini`, deployment type **Global Standard** (the chat model)
   - `text-embedding-3-small`, **Global Standard** (the embedding model)
   (Claude Haiku wasn't available on Global Standard due to quota, so `gpt-4.1-mini` was used.)
5. **Copy the credentials**: in portal.azure.com open the Foundry resource → **Resource Management → Keys and endpoint**:
   - **KEY 1** goes in `LLM_API_KEY`
   - **Endpoint** (`https://<name>.services.ai.azure.com`) goes in `LLM_ENDPOINT`
   - **Azure OpenAI endpoint** (`https://<name>.openai.azure.com`) goes in `EMBEDDING_ENDPOINT`
6. **Set a budget**: Cost Management → Budgets → Add, for example $5/month with an email alert.
7. **Fill in `.env`** (see section 7, step 3) and restart the backend.

> 🔐 The key lives only in `.env`, which is git-ignored. If a key ever leaks, click **Regenerate** next to it in "Keys and endpoint".

---

## 6. What runs locally and what runs on Azure

| On your laptop (Docker) | On Azure AI Foundry |
|---|---|
| Cloning / receiving the repository | Converting chunks to vectors (`text-embedding-3-small`) |
| Scanning, hashing, parsing, chunking | Converting your question to a vector |
| Storing everything in PostgreSQL + pgvector | Writing the answer (`gpt-4.1-mini`) |
| Searching for relevant code | |
| Choosing the agent, building the prompt, checking citations | |
| Chat history and memory | |

Only the small code chunks needed for a question (plus the chunks during indexing) are sent to Azure. The rest of the work stays on your machine.

**Why not fully local?** Running a language model on a CPU-only laptop was about 10 words per second, so answers took 3–5 minutes, and the small models that fit were less accurate. Azure answers in about 5–15 seconds with much better quality. The local Ollama option is still there for fully offline use: set `LLM_PROVIDER=ollama` and `EMBEDDING_PROVIDER=ollama`.

---

## 7. Installation: every command, and why

### Step 1: Install the tools (once per laptop)
| Tool | Why |
|---|---|
| **Docker Desktop** | Runs the database, backend and frontend without installing Python, Node or PostgreSQL by hand |
| **Git** | Downloads the project from GitHub and lets you commit changes |
| *(optional)* **Python 3.11+** and **Node 20+** | Only needed to run tests and builds outside Docker |

### Step 2: Get the code
```powershell
git clone https://github.com/Abdurrehman0815/repomind-ai.git
cd repomind-ai
```
`git clone` downloads the project, and `cd` moves into the folder.

### Step 3: Create your settings file
```powershell
Copy-Item .env.example .env
notepad .env
```
`.env.example` is a template with no secrets, and it's committed to GitHub. `.env` is your private copy holding the Azure key, and it's never committed. Fill in the `LLM_*` and `EMBEDDING_*` values from section 5.

### Step 4: Build and start everything
```powershell
docker compose up -d --build
```
- `docker compose` reads `docker-compose.yml`, which describes the three services.
- `up` creates and starts them.
- `-d` (detached) runs them in the background so your terminal is free.
- `--build` rebuilds the images from source. Use it the first time, and after changing `Dockerfile`, `requirements.txt`, `package.json` or frontend code.

### Step 5: Create the database tables (first time only)
```powershell
docker compose exec backend alembic upgrade head
```
`exec backend` runs a command inside the running backend container. `alembic upgrade head` applies all database **migrations**, the scripts in `backend/alembic/versions/` that create the tables.

### Step 6: Use it
Open http://localhost:3000. Go to **Projects**, then **Import Repository**, wait for **indexed**, then ask questions in **Chat**. Hover the dot at the bottom-left of the sidebar to check service health.

### Development-only commands (outside Docker)
| Command | Where | When / why |
|---|---|---|
| `python -m venv venv` | `backend/` | Create an isolated Python environment (once) |
| `.\venv\Scripts\Activate.ps1` | `backend/` | Use that environment in this terminal |
| `pip install -r requirements.txt` | `backend/` | Install backend libraries (once, and after `requirements.txt` changes) |
| `pytest` | `backend/` | Run the 147 backend unit tests before committing |
| `..\backend\venv\Scripts\python.exe -m pytest` | `mcp-server/` | Run the 27 MCP tool tests |
| `npm install` | `frontend/` | Install frontend libraries (once, and after `package.json` changes) |
| `npm run build` | `frontend/` | Type-check and build the production frontend |
| `npm run lint` | `frontend/` | Check frontend code style |
| `python -m evals.run` | project root | With the stack running, measure answer grounding on the sample repo |

---

## 8. Docker explained

### The problem Docker solves
Without Docker, running RepoMind means installing the right versions of Python, Node, PostgreSQL and the pgvector extension, then configuring them. If any version differs ("works on my machine"), things break. Docker packages each part **with everything it needs**, so it runs the same on any computer.

### The five words you need
| Word | Meaning | In RepoMind |
|---|---|---|
| **Image** | A frozen, ready-to-run package of an app plus its dependencies, like an installer | `repomind-ai-backend`, `repomind-ai-frontend`, `pgvector/pgvector:pg16` |
| **Container** | A running copy of an image, like an app that's open | `repomind-backend`, `repomind-frontend`, `repomind-postgres` |
| **Dockerfile** | The recipe for building an image | `backend/Dockerfile`, `frontend/Dockerfile` |
| **Volume** | A storage folder managed by Docker that survives container restarts and rebuilds | `postgres_data` (the database), `workspace_data` (cloned repos) |
| **Compose** | One file that starts several containers together and connects them | `docker-compose.yml` |

### The three containers
| Container | What it is | Port on your laptop |
|---|---|---|
| `repomind-postgres` | PostgreSQL 16 with pgvector. Data lives in the `postgres_data` volume | `5434` |
| `repomind-backend` | FastAPI app (Python 3.11) | `8000` |
| `repomind-frontend` | React app built and served by Nginx, which also forwards `/api` to the backend | `3000` |

The containers talk to each other by name on a private network (`repomind-net`). For example, the backend reaches the database at `postgres:5432`. The port numbers on the left side of the mapping (`5434:5432`) are just how *your laptop* reaches them. Port 5434 is used because another project on this laptop already uses 5433.

### Two compose files
- `docker-compose.yml` is the base definition, used everywhere.
- `docker-compose.override.yml` holds **development extras** that Docker applies automatically: it mounts `./backend` into the container and runs with `--reload`, so backend code changes apply without rebuilding.

### Why rebuilds are fast after the first time
Docker builds images in layers and caches each one. If `requirements.txt` didn't change, the "install libraries" layer is reused, and only your changed code is copied again.

---

## 9. Moving the project to another laptop

This is where Docker pays off.

### Option A: fresh start (recommended)
On the new laptop:
```powershell
# 1. Install Docker Desktop and Git
git clone https://github.com/Abdurrehman0815/repomind-ai.git
cd repomind-ai
Copy-Item .env.example .env        # then paste your Azure values into .env
docker compose up -d --build
docker compose exec backend alembic upgrade head
```
Open http://localhost:3000 and re-import your repositories. Indexing with Azure takes seconds to a minute.

> **Why the key isn't on GitHub:** `.env` is ignored by git, so you copy the values yourself, or carry the `.env` file over on a USB stick or password manager. This keeps your key private.

### Option B: also move the existing database (keep indexed repos and chat history)
On the **old** laptop, export the database to a file:
```powershell
docker compose exec -T postgres pg_dump -U repomind -d repomind > repomind-backup.sql
```
Copy `repomind-backup.sql` and `.env` to the new laptop. After Option A's steps there, import it:
```powershell
Get-Content repomind-backup.sql | docker compose exec -T postgres psql -U repomind -d repomind
```
`pg_dump` writes the whole database as SQL, and `psql` replays it. (Re-importing repositories as in Option A is usually simpler.)

### What carries over automatically
| Thing | How |
|---|---|
| Exact Python, Node, PostgreSQL and pgvector versions | Pinned in the Dockerfiles and `requirements.txt` / `package-lock.json` |
| Database schema | Alembic migrations |
| Settings | `.env` (you copy it) |
| Your indexed data | Re-import, or Option B |

---

## 10. Everyday command cheat sheet

Run these from the `repomind-ai` folder.

| I want to… | Command |
|---|---|
| Start everything | `docker compose up -d` |
| Start after changing frontend code / dependencies | `docker compose up -d --build` |
| Apply a `.env` change | `docker compose up -d backend` |
| Stop everything (data is kept) | `docker compose down` |
| See what's running | `docker compose ps` |
| See backend logs (last 60 lines) | `docker compose logs backend --tail 60` |
| Follow logs live | `docker compose logs -f backend` |
| Restart the backend | `docker compose restart backend` |
| Open a database shell | `docker compose exec postgres psql -U repomind -d repomind` |
| Run migrations | `docker compose exec backend alembic upgrade head` |
| Delete everything **including data** ⚠️ | `docker compose down -v` |

---

## 11. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Sidebar dot is orange or red | A service is failing | Hover the dot: it lists each service and the error |
| `401` in backend logs | Wrong Azure key | Re-copy KEY 1 into `LLM_API_KEY`, then `docker compose up -d backend` |
| `404` in backend logs | Wrong endpoint or deployment name | Check `LLM_ENDPOINT`, `LLM_MODEL`, `EMBEDDING_MODEL` against the Foundry portal |
| Project shows **Error** | One file failed badly or Azure was unreachable | `docker compose logs backend --tail 60`, fix the cause, delete and re-import |
| "No evidence" for everything after switching embedding models | Old vectors came from a different model | Delete and re-import repositories |
| `port is already allocated` | Another app uses 3000/8000/5434 | Stop that app, or change the left port in `docker-compose.yml` |
| Backend `unhealthy` after moving folders | Containers point at the old folder | `docker compose up -d --build` from the new folder |

---

## 12. Where things live in the code

| I want to change… | Look in |
|---|---|
| How files are scanned or skipped | `backend/app/ingestion/scanner.py` |
| How code is split into chunks | `backend/app/ingestion/chunker.py` |
| The Azure chat / embedding calls | `backend/app/ai/providers/azure_foundry.py`, `azure_embedding.py` |
| Which provider is used | `backend/app/ai/providers/registry.py`, `embedding_registry.py` (driven by `.env`) |
| Search ranking | `backend/app/services/retrieval_service.py` |
| How a question is routed to an agent | `backend/app/services/supervisor_service.py` (`_classify_intent`) |
| A specialist agent's prompt | `backend/app/agents/*.py` |
| API endpoints | `backend/app/api/v1/` |
| Database tables | `backend/app/models/` + a new migration in `backend/alembic/versions/` |
| The UI pages | `frontend/src/pages/` (Dashboard, Projects, Workspace = Chat) |
| MCP tools | `mcp-server/app/tools/` |
| Settings and defaults | `backend/app/core/config.py` and `.env` |

---

## 13. Glossary

| Term | Meaning |
|---|---|
| **RAG** | Retrieve relevant documents, then have the model answer from them |
| **Embedding / vector** | A list of numbers that represents the meaning of text; similar meaning gives nearby vectors |
| **pgvector** | PostgreSQL extension that stores vectors and finds the nearest ones quickly |
| **Hybrid search** | Combining meaning-based (vector) search with exact-word (keyword) search |
| **RRF** | Reciprocal Rank Fusion: merges two ranked lists by position |
| **Chunk** | A piece of a file (about 512 tokens) that is embedded and retrieved |
| **Token** | A word-piece; models read and write tokens |
| **LangGraph** | Library for building agent workflows as a graph of steps |
| **MCP** | Model Context Protocol: a standard way to expose tools to AI agents |
| **Migration** | A versioned script that changes the database structure |
| **Deployment (Azure)** | A model you've enabled in Foundry, called by its deployment name |
