# Postgres 16 with PostGIS (geo) + pgvector (embeddings) — the single DB engine for
# Chronos. Based on the official PostGIS image (Debian + PGDG apt repo), then add pgvector.
FROM postgis/postgis:16-3.4

# pgvector ships as a PGDG package for the matching major version.
RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-16-pgvector \
    && rm -rf /var/lib/apt/lists/*
