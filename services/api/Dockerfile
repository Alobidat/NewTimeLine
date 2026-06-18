# Chronos Event API image. Build context = repo root (needs packages/core too).
FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

# Install the shared core first (better layer caching), then the service.
COPY packages/core /app/packages/core
COPY services/api /app/services/api
RUN pip install ./packages/core ./services/api

EXPOSE 8000
# Single worker for dev; scale via replicas/gunicorn in later phases.
CMD ["uvicorn", "chronos_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
