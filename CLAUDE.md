# Waltham Comments

Automated pipeline that downloads Waltham city council meeting videos, transcribes and diarizes them with WhisperX, and serves them through a searchable web UI.

## Architecture

Four containerized services, orchestrated by `compose.yml`:

| Service | Directory | Purpose |
|---|---|---|
| Meeting Downloader | `meeting-downloader/` | Polls Telvue API, downloads HLS video streams, extracts audio |
| Transcription | `transcription-service/` | Transcribes + diarizes WAV files with WhisperX |
| Web App | `waltham-comments-page/` | FastAPI backend + React frontend for viewing meetings |
| Embeddings | `embeddings-service/` | HTTP API for sentence embeddings (future semantic search) |

Services communicate via shared Docker volumes — no message queues. Data flows: `videos/` → `audio/` → `transcriptions/`. The transcription service also maintains a speaker embedding database at `data/speaker_db.pkl` to match speakers across meetings.

## Running the Project

```bash
# Start all services
docker compose up --build

# Web UI:       http://localhost:8000
# Embeddings:   http://localhost:8001
```

Requires a `.env` file with:
- `HF_TOKEN` — Hugging Face token (required for WhisperX diarization model)
- `DATA_DIR` — root data directory (mapped to `/app` in containers)

Optional env vars: `POLL_INTERVAL_SECONDS` (default 3600), `MIN_SPEAKERS` (default 5), `MAX_SPEAKERS` (default 18), `MODELS_DIR` (default `models`), `CPU_THREADS` (default 0 = all cores).

## Development

**Package manager:** `uv` with `pyproject.toml` — never use `pip` or `requirements.txt`.

Each service has its own `pyproject.toml`. The root `pyproject.toml` covers shared dependencies and test tooling.

```bash
uv sync           # install deps
uv run pytest     # run tests
```

**Python version:** 3.13 (see `.python-version`).

**PyTorch:** installed from PyPI (CPU build). No custom index is needed.

## Key Files

- `compose.yml` — Docker Compose orchestration and volume mounts
- `settings.yaml` — Telvue API config (player ID, playlist IDs for each board)
- `monitoring.py` — shared `setup_logging()` helper; copied into each container image at build time

## Logging

Use `monitoring.setup_logging(name)` to get a named logger — don't call `logging.basicConfig()` or use the root `logging` logger directly. Always call `logger.info(...)` on the returned logger object, not `logging.info(...)`.

## Speaker Identification

On the first processed meeting, the transcription service builds a speaker embedding database. Subsequent meetings match speakers using cosine similarity (threshold: 0.7). Unmatched speakers are labeled `"DEFAULT"`. The first meeting used to seed the database should be one without public comment (council members only).

## Web App Frontend

The frontend is a React 19 / Vite app in `waltham-comments-page/frontend/`. Build it before starting the container:

```bash
cd waltham-comments-page/frontend
npm install
npm run build
```

The FastAPI backend serves the built `dist/` directory as static files.
