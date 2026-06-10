FROM nvidia/cuda:12.8.1-cudnn-runtime-ubuntu24.04

RUN apt update && apt install -y ffmpeg

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

COPY transcription-service/pyproject.toml .
RUN uv sync --no-dev

COPY transcription-service/main.py transcription-service/transcription.py \
     transcription-service/identification.py .
COPY monitoring.py .

CMD ["uv", "run", "python", "main.py"]
