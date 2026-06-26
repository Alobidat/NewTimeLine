# Chronos agents image (Phase 1: Tier-1 ingest + seed). Build context = repo root.
FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

# ffmpeg/ffprobe: media-probe measures clips + extracts posters; the news-anchor agent also
# shells out to ffmpeg (drawtext/zoompan) to compose captioned explainer videos. fonts-dejavu-core
# provides the TTF drawtext burns the headline/captions with.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# Piper TTS (offline, CPU) for news-anchor narration, plus a bundled English voice.
RUN pip install "piper-tts==1.4.2"
ADD https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/medium/en_US-amy-medium.onnx /opt/piper/en_US-amy-medium.onnx
ADD https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/medium/en_US-amy-medium.onnx.json /opt/piper/en_US-amy-medium.onnx.json

COPY packages/core /app/packages/core
COPY services/agents /app/services/agents
RUN pip install ./packages/core ./services/agents

# Default to the RSS ingestor; override the command for seeding, e.g.:
#   docker compose run --rm agents seed-wikidata --limit 300
ENTRYPOINT ["chronos-agents"]
CMD ["ingest-rss"]
