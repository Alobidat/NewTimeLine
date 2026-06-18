# Chronos agents image (Phase 1: Tier-1 ingest + seed). Build context = repo root.
FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

COPY packages/core /app/packages/core
COPY services/agents /app/services/agents
RUN pip install ./packages/core ./services/agents

# Default to the RSS ingestor; override the command for seeding, e.g.:
#   docker compose run --rm agents seed-wikidata --limit 300
ENTRYPOINT ["chronos-agents"]
CMD ["ingest-rss"]
