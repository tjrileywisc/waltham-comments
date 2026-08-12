FROM nvidia/cuda:12.8.1-cudnn-runtime-ubuntu24.04

RUN apt update && apt install -y ffmpeg

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

COPY transcription_service/pyproject.toml .
RUN uv sync --no-dev

COPY transcription_service/main.py transcription_service/transcription.py \
     transcription_service/healthcheck.py \
     transcription_service/identification.py transcription_service/db.py \
     transcription_service/relabel.py .
COPY monitoring.py log_config.json .

CMD ["uv", "run", "python", "main.py"]
