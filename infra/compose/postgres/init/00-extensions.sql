-- Runs once on first DB init (docker-entrypoint-initdb.d).
-- Enables the extensions the schema depends on. Schema migrations live in db/ (Phase 1+).
CREATE EXTENSION IF NOT EXISTS postgis;       -- geospatial (geom columns, GiST indexes)
CREATE EXTENSION IF NOT EXISTS vector;        -- pgvector (embeddings, HNSW indexes)
CREATE EXTENSION IF NOT EXISTS pg_trgm;       -- trigram text search (fuzzy match, FTS aid)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";   -- uuid helpers (gen_random_uuid is core in pg16)
