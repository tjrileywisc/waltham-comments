FROM python:3.13-slim

RUN apt-get update && apt-get install -y npm \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

COPY pyproject.toml main.py .
COPY lib/ lib/
COPY frontend/ frontend/
RUN uv sync --no-dev

RUN cd frontend && npm ci && npm run build

CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
