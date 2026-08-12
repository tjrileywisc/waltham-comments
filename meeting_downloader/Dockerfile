FROM python:3.13-slim

RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

COPY meeting_downloader/pyproject.toml .
RUN uv sync --no-dev

RUN uv run playwright install chromium --with-deps

COPY meeting_downloader/main.py meeting_downloader/downloader.py meeting_downloader/publicmeeting.py meeting_downloader/audio.py .
COPY monitoring.py log_config.json .
COPY settings.yaml .

CMD ["uv", "run", "python", "main.py"]
