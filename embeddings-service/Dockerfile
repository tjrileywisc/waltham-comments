FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

COPY embeddings-service/pyproject.toml .
RUN uv sync --no-dev

COPY embeddings-service/main.py embeddings-service/sentence_embeddings.py .

CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
