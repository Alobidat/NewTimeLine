# One-shot migration runner: `alembic upgrade head`. Build context = repo root.
FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

COPY packages/core /app/packages/core
COPY db /app/db
RUN pip install ./packages/core alembic

WORKDIR /app/db
CMD ["alembic", "upgrade", "head"]
