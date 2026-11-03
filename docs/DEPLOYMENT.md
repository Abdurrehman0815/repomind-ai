# RepoMind AI — Deployment Guide

## Local Development (Default)

See README.md for the primary local setup.

```bash
docker compose up -d
cd backend && alembic upgrade head
cd frontend && npm run dev
```

---

## Environment Variables Reference

All configuration is via environment variables. See `.env.example` for the full list.

### Core

| Variable | Default | Description |
|---|---|---|
| `ENVIRONMENT` | `development` | `development`, `production` |
| `DEBUG` | `false` | Enable debug logging |
| `SECRET_KEY` | — | Application secret key (required) |

### Database

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | — | PostgreSQL connection URL |
| `DB_POOL_SIZE` | `10` | Connection pool size |
| `DB_MAX_OVERFLOW` | `20` | Max overflow connections |

### AI Providers

| Variable | Default | Description |
|---|---|---|
| `LLM_PROVIDER` | `ollama` | `azure_foundry` (recommended) or `ollama` |
| `LLM_ENDPOINT` | — | Foundry endpoint, `https://<resource>.services.ai.azure.com` |
| `LLM_API_KEY` | — | Foundry key (KEY 1); `.env` only, never committed |
| `LLM_MODEL` | — | Chat deployment name, e.g. `gpt-4.1-mini` |
| `LLM_API_STYLE` | `anthropic` | `openai` for GPT deployments, `anthropic` for Claude |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_MODEL` | `llama3.2` | Ollama model to use |
| `EMBEDDING_PROVIDER` | `local` | `azure_foundry`, `ollama` or `local` |
| `EMBEDDING_MODEL` | `nomic-embed-text` | Embedding model / deployment, e.g. `text-embedding-3-small` |
| `EMBEDDING_DIMENSIONS` | `768` | Vector dimensions (must match the database schema) |
| `EMBEDDING_ENDPOINT` | — | Azure OpenAI endpoint, `https://<resource>.openai.azure.com` |
| `RETRIEVAL_MIN_SIMILARITY` | `0.5` | Vector-search cutoff; use `0.2` for Azure embeddings |

### Security

| Variable | Default | Description |
|---|---|---|
| `WORKSPACE_ROOT` | — | Base path for repository storage |
| `MAX_FILE_SIZE_MB` | `10` | Maximum file size to index |
| `TOOL_EXECUTION_TIMEOUT` | `60` | Tool execution timeout (seconds) |

---

## Docker Compose Services

```yaml
services:
  postgres:    # PostgreSQL 16 + pgvector (host port 5434)
  backend:     # FastAPI application (port 8000)
  frontend:    # React build served by Nginx (port 3000)
```

---

## Production Deployment (Future)

For production deployments, consider:

1. **Reverse proxy** — nginx or Caddy in front of frontend + backend
2. **Process manager** — systemd or supervisor for backend
3. **Database** — managed PostgreSQL (RDS, Supabase, Neon) with pgvector
4. **TLS** — terminate at reverse proxy
5. **Secrets** — environment variables from a secrets manager

### Optional Azure Production Stack

Only implement if cloud hosting is required (the AI models already run on Azure AI Foundry):

- **Azure Container Apps** — run the backend and frontend containers
- **Azure Database for PostgreSQL** — managed database with the pgvector extension
- **Azure Key Vault** — store `LLM_API_KEY` instead of a `.env` file
- **Azure Monitor / Application Insights** — logs and metrics

Do not add these unless specifically required. The local Docker Compose
setup is the primary deployment target.

---

## Health Checks

```bash
# Backend health
curl http://localhost:8000/health

# Database connectivity
curl http://localhost:8000/health/db

# Ollama connectivity  
curl http://localhost:8000/health/ollama

# Full startup check
curl http://localhost:8000/health/full
```

---

## Backup and Recovery

Database backup:
```bash
docker compose exec postgres pg_dump -U repomind repomind > backup.sql
```

Database restore:
```bash
docker compose exec -T postgres psql -U repomind repomind < backup.sql
```
