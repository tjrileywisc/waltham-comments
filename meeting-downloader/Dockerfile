FROM python:3.13-slim

RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

COPY meeting-downloader/pyproject.toml .
RUN uv sync --no-dev

RUN uv run playwright install chromium --with-deps

COPY meeting-downloader/main.py meeting-downloader/downloader.py meeting-downloader/publicmeeting.py meeting-downloader/audio.py .
COPY monitoring.py log_config.json .
COPY settings.yaml .

CMD ["uv", "run", "python", "main.py"]
