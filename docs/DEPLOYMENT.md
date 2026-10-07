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
| `LLM_PROVIDER` | `ollama` | `ollama` or `bedrock` |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_MODEL` | `llama3.2` | Ollama model to use |
| `EMBEDDING_PROVIDER` | `local` | Embedding provider |
| `EMBEDDING_MODEL` | `nomic-embed-text` | Embedding model name |
| `EMBEDDING_DIMENSIONS` | `768` | Vector dimensions |

### AWS Bedrock (Phase 32+ only)

| Variable | Default | Description |
|---|---|---|
| `AWS_REGION` | — | AWS region |
| `BEDROCK_MODEL_ID` | — | Bedrock model ID |

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
  postgres:    # PostgreSQL 15 + pgvector
  backend:     # FastAPI application
  frontend:    # React/Vite application
  ollama:      # Ollama inference server (optional)
```

---

## Production Deployment (Future)

For production deployments, consider:

1. **Reverse proxy** — nginx or Caddy in front of frontend + backend
2. **Process manager** — systemd or supervisor for backend
3. **Database** — managed PostgreSQL (RDS, Supabase, Neon) with pgvector
4. **TLS** — terminate at reverse proxy
5. **Secrets** — environment variables from a secrets manager

### Optional AWS Production Stack (Phase 36+)

Only implement if AWS production deployment is required:

- **ECS/Fargate** — container compute
- **RDS PostgreSQL** — managed database with pgvector
- **S3** — repository storage
- **CloudWatch** — logging and metrics
- **Secrets Manager** — credential management
- **IAM** — role-based access control

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
