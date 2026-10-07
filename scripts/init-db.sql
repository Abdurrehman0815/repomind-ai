-- Initialize pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS btree_gin;

-- Verify extensions
SELECT extname, extversion FROM pg_extension WHERE extname IN ('vector', 'pg_trgm');
