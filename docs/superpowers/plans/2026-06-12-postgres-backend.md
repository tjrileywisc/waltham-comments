# Postgres Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace per-meeting CSV files with a PostgreSQL + pgvector backend, enabling real vector similarity search in the webapp.

**Architecture:** psycopg3 (sync) throughout. The transcription service writes utterances and their rolling-window embeddings to Postgres after each meeting. The webapp reads transcripts from Postgres and runs pgvector cosine-similarity queries for search. A one-time migration script imports existing CSVs.

**Tech Stack:** PostgreSQL 17, pgvector extension, `pgvector/pgvector:pg17` Docker image, `psycopg[binary]>=3.2.0`, `requests`.

---

## File Map

**Created:**
- `init.sql` — schema: `utterances`, `utterance_embeddings`, HNSW index
- `transcription-service/db.py` — `build_window_text`, `save_meeting`
- `webapp/lib/db.py` — `connect`, `get_transcript`
- `migrate_csv_to_db.py` — one-time import of existing CSV files
- `tests/test_transcription_db.py` — tests for `build_window_text` and `save_meeting`
- `tests/test_webapp_db.py` — tests for webapp transcript read and search

**Modified:**
- `compose.yml` — add postgres service, expose port 5432, add `DATABASE_URL` + `EMBEDDINGS_SERVICE_URL` to transcription-service and web
- `transcription-service/pyproject.toml` — add `psycopg[binary]`, `requests`
- `transcription-service/Dockerfile` — add `db.py` to COPY list
- `transcription-service/transcription.py` — replace CSV write with `save_meeting`; remove pandas
- `webapp/pyproject.toml` — add `psycopg[binary]`, `requests`
- `webapp/main.py` — replace CSV read with `lib.db.get_transcript`
- `webapp/lib/search.py` — implement real pgvector search
- `pyproject.toml` (root) — add `psycopg[binary]` so tests can import it
- `conftest.py` — add `webapp` to sys.path

---

## Task 1: Infrastructure — postgres service and schema

**Files:**
- Create: `init.sql`
- Modify: `compose.yml`
- Modify: `.env`

- [ ] **Step 1: Write init.sql**

Create `init.sql` at the project root:

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE utterances (
    id            SERIAL PRIMARY KEY,
    meeting_name  TEXT NOT NULL,
    segment_index INTEGER NOT NULL,
    start_time    FLOAT NOT NULL,
    end_time      FLOAT NOT NULL,
    text          TEXT NOT NULL,
    speaker       TEXT NOT NULL,
    UNIQUE (meeting_name, segment_index)
);

CREATE TABLE utterance_embeddings (
    utterance_id INTEGER PRIMARY KEY REFERENCES utterances(id) ON DELETE CASCADE,
    embedding    vector(384) NOT NULL
);

CREATE INDEX ON utterance_embeddings USING hnsw (embedding vector_cosine_ops);
```

- [ ] **Step 2: Replace compose.yml with the updated version**

```yaml
name: waltham-comments
services:
  postgres:
    image: pgvector/pgvector:pg17
    environment:
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB}
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./init.sql:/docker-entrypoint-initdb.d/init.sql
  embeddings-service:
    build:
      context: .
      dockerfile: embeddings-service/Dockerfile
    image: embeddings-service
    ports:
      - "8001:8001"
    volumes:
      - C:/workspace/waltham-comments/models:/app/models
  meeting-downloader:
    build:
      context: .
      dockerfile: meeting-downloader/Dockerfile
    image: meeting-downloader
    volumes:
      - C:/workspace/waltham-comments/videos:/app/videos
      - C:/workspace/waltham-comments/audio:/app/audio
  transcription-service:
    build:
      context: .
      dockerfile: transcription-service/Dockerfile
    image: transcription-service
    env_file:
      - .env
    environment:
      DATABASE_URL: postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB}
      EMBEDDINGS_SERVICE_URL: http://embeddings-service:8001
    depends_on:
      - postgres
      - embeddings-service
    volumes:
      - C:/workspace/waltham-comments/audio:/app/audio
      - C:/workspace/waltham-comments/data:/app/data
      - C:/workspace/waltham-comments/models:/app/models
  web:
    build:
      context: .
      dockerfile: webapp/Dockerfile
    image: comments-web
    env_file:
      - .env
    environment:
      DATABASE_URL: postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB}
      EMBEDDINGS_SERVICE_URL: http://embeddings-service:8001
    ports:
      - "8000:8000"
    depends_on:
      - postgres
    volumes:
      - C:/workspace/waltham-comments/videos:/app/videos
      - C:/workspace/waltham-comments/data:/app/data

volumes:
  postgres_data:
```

Note: the `transcriptions` volume mount is removed from both services — CSV files are no longer used.

- [ ] **Step 3: Add postgres vars to .env**

Append to `.env`:

```
POSTGRES_USER=waltham
POSTGRES_PASSWORD=waltham_dev
POSTGRES_DB=waltham
```

- [ ] **Step 4: Verify postgres starts and schema is applied**

```bash
docker compose up postgres -d
docker compose exec postgres psql -U waltham -d waltham -c "\dt"
```

Expected output: two rows — `utterance_embeddings` and `utterances`.

- [ ] **Step 5: Commit**

```bash
git add init.sql compose.yml .env
git commit -m "feat: add postgres+pgvector service and schema"
```

---

## Task 2: Add psycopg dependencies

**Files:**
- Modify: `transcription-service/pyproject.toml`
- Modify: `webapp/pyproject.toml`
- Modify: `pyproject.toml` (root)

- [ ] **Step 1: Update transcription-service/pyproject.toml**

```toml
[project]
name = "transcription-service"
version = "0.1.0"
description = "Diarizes and transcribes Waltham public meeting audio"
requires-python = "==3.13.*"
dependencies = [
    "huggingface-hub>=0.36.0",
    "pandas>=2.0.0",
    "psycopg[binary]>=3.2.0",
    "requests>=2.32.0",
    "scikit-learn>=1.0.0",
    "tensorboard>=2.20.0",
    "torch>=2.8.0",
    "torchaudio>=2.8.0",
    "torchvision>=0.20.0",
    "whisperx>=3.7.6",
]

[[tool.uv.index]]
name = "pytorch-cpu"
url = "https://download.pytorch.org/whl/cpu"
explicit = true

[tool.uv.sources]
torch = [{ index = "pytorch-cpu" }]
torchaudio = [{ index = "pytorch-cpu" }]
torchvision = [{ index = "pytorch-cpu" }]
```

- [ ] **Step 2: Update webapp/pyproject.toml**

```toml
[project]
name = "waltham-comments-page"
version = "0.1.0"
description = "Add your description here"
readme = "README.md"
requires-python = ">=3.13"
dependencies = [
    "fastapi>=0.128.1",
    "psycopg[binary]>=3.2.0",
    "requests>=2.32.0",
    "uvicorn>=0.40.0",
]
```

- [ ] **Step 3: Add psycopg to root pyproject.toml**

In `pyproject.toml`, add `"psycopg[binary]>=3.2.0"` to the `dependencies` list so tests can import psycopg when mocking.

- [ ] **Step 4: Sync and verify**

```bash
uv sync
```

Expected: resolves without errors.

- [ ] **Step 5: Commit**

```bash
git add transcription-service/pyproject.toml webapp/pyproject.toml pyproject.toml uv.lock
git commit -m "feat: add psycopg and requests dependencies"
```

---

## Task 3: Rolling window text builder (TDD)

**Files:**
- Create: `transcription-service/db.py`
- Create: `tests/test_transcription_db.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_transcription_db.py`:

```python
from db import build_window_text


def test_build_window_text_includes_preceding_segments_within_window():
    segments = [
        {"start": 0.0, "end": 1.0, "text": "Hello"},
        {"start": 1.5, "end": 2.5, "text": "world"},
        {"start": 3.0, "end": 4.0, "text": "today"},
    ]
    # window_start = 4.0 - 5.0 = -1.0; all three start times >= -1.0
    assert build_window_text(segments, 2) == "Hello world today"


def test_build_window_text_excludes_segments_outside_window():
    segments = [
        {"start": 0.0, "end": 1.0, "text": "Old"},
        {"start": 5.0, "end": 6.0, "text": "Recent"},
        {"start": 7.0, "end": 8.0, "text": "Current"},
    ]
    # window_start = 8.0 - 5.0 = 3.0; "Old" starts at 0.0 < 3.0, excluded
    assert build_window_text(segments, 2) == "Recent Current"


def test_build_window_text_long_segment_used_alone():
    segments = [
        {"start": 0.0, "end": 1.0, "text": "Before"},
        {"start": 2.0, "end": 10.0, "text": "Long segment"},
    ]
    # duration 8.0 >= 5.0 — use alone regardless of preceding segments
    assert build_window_text(segments, 1) == "Long segment"


def test_build_window_text_first_segment():
    segments = [{"start": 0.0, "end": 2.0, "text": "First"}]
    assert build_window_text(segments, 0) == "First"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_transcription_db.py -v
```

Expected: `ImportError: cannot import name 'build_window_text' from 'db'` (file doesn't exist yet).

- [ ] **Step 3: Create transcription-service/db.py with build_window_text**

```python
import os
import requests
import psycopg

EMBEDDINGS_SERVICE_URL = os.environ.get("EMBEDDINGS_SERVICE_URL", "http://embeddings-service:8001")


def build_window_text(segments: list[dict], current_idx: int) -> str:
    current = segments[current_idx]
    if current["end"] - current["start"] >= 5.0:
        return current["text"]
    window_start = current["end"] - 5.0
    parts = [seg["text"] for seg in segments[:current_idx] if seg["start"] >= window_start]
    parts.append(current["text"])
    return " ".join(parts)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_transcription_db.py -v
```

Expected: all 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add transcription-service/db.py tests/test_transcription_db.py
git commit -m "feat: add rolling window text builder"
```

---

## Task 4: Transcription service write path (TDD)

**Files:**
- Modify: `transcription-service/db.py` (add `save_meeting`)
- Modify: `tests/test_transcription_db.py` (add `save_meeting` tests)
- Modify: `transcription-service/transcription.py` (replace CSV write)
- Modify: `transcription-service/Dockerfile` (copy `db.py`)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_transcription_db.py`:

```python
from unittest.mock import MagicMock


def test_save_meeting_inserts_utterances_and_embeddings(mocker):
    segments = [
        {"start": 0.0, "end": 2.0, "text": "Hello", "speaker": "SPEAKER_00"},
        {"start": 2.5, "end": 4.0, "text": "World", "speaker": "SPEAKER_01"},
    ]

    mock_cur = MagicMock()
    mock_cur.fetchall.return_value = [(1,), (2,)]
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

    mock_resp = MagicMock()
    mock_resp.json.return_value = {"embeddings": [[0.1] * 384, [0.2] * 384]}
    mocker.patch("db.requests.post", return_value=mock_resp)

    from db import save_meeting
    save_meeting(mock_conn, "Test Meeting 1-1-26", segments)

    mock_cur.executemany.assert_called_once()
    insert_sql, rows = mock_cur.executemany.call_args.args
    assert "INSERT INTO utterances" in insert_sql
    assert len(rows) == 2
    assert rows[0] == ("Test Meeting 1-1-26", 0, 0.0, 2.0, "Hello", "SPEAKER_00")
    assert rows[1] == ("Test Meeting 1-1-26", 1, 2.5, 4.0, "World", "SPEAKER_01")

    assert mock_conn.commit.call_count == 2

    embedding_calls = [
        c for c in mock_cur.execute.call_args_list
        if "utterance_embeddings" in c.args[0]
    ]
    assert len(embedding_calls) == 2


def test_save_meeting_uses_default_speaker_when_missing(mocker):
    segments = [{"start": 0.0, "end": 1.0, "text": "Hello"}]  # no "speaker" key

    mock_cur = MagicMock()
    mock_cur.fetchall.return_value = [(1,)]
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

    mock_resp = MagicMock()
    mock_resp.json.return_value = {"embeddings": [[0.0] * 384]}
    mocker.patch("db.requests.post", return_value=mock_resp)

    from db import save_meeting
    save_meeting(mock_conn, "Test Meeting", segments)

    _, rows = mock_cur.executemany.call_args.args
    assert rows[0][5] == "DEFAULT"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_transcription_db.py::test_save_meeting_inserts_utterances_and_embeddings tests/test_transcription_db.py::test_save_meeting_uses_default_speaker_when_missing -v
```

Expected: `ImportError: cannot import name 'save_meeting' from 'db'`.

- [ ] **Step 3: Add save_meeting to transcription-service/db.py**

Append to `transcription-service/db.py` (after `build_window_text`):

```python
def save_meeting(conn, meeting_name: str, segments: list[dict]) -> None:
    windowed_texts = [build_window_text(segments, i) for i in range(len(segments))]

    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO utterances (meeting_name, segment_index, start_time, end_time, text, speaker)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (meeting_name, segment_index) DO NOTHING
            """,
            [
                (meeting_name, i, seg["start"], seg["end"], seg["text"], seg.get("speaker", "DEFAULT"))
                for i, seg in enumerate(segments)
            ],
        )
        cur.execute(
            "SELECT id FROM utterances WHERE meeting_name = %s ORDER BY segment_index",
            (meeting_name,),
        )
        ids = [row[0] for row in cur.fetchall()]
    conn.commit()

    resp = requests.post(
        f"{EMBEDDINGS_SERVICE_URL}/embeddings",
        json={"sentences": windowed_texts},
        timeout=120,
    )
    resp.raise_for_status()
    embeddings = resp.json()["embeddings"]

    with conn.cursor() as cur:
        for uid, embedding in zip(ids, embeddings):
            vec_str = "[" + ",".join(str(x) for x in embedding) + "]"
            cur.execute(
                "INSERT INTO utterance_embeddings (utterance_id, embedding) VALUES (%s, %s::vector)"
                " ON CONFLICT DO NOTHING",
                (uid, vec_str),
            )
    conn.commit()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_transcription_db.py -v
```

Expected: all 6 tests PASS.

- [ ] **Step 5: Replace transcription-service/transcription.py**

Remove the pandas import and CSV write; replace with a DB call. Full updated file:

```python
import gc
import os
import psycopg

from identification import Identifier
from db import save_meeting

import torch
import whisperx
from whisperx.diarize import DiarizationPipeline

from monitoring import setup_logging

logger = setup_logging("transcription")

os.environ["TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD"] = "1"

HF_TOKEN = os.environ.get("HF_TOKEN", "")
MIN_SPEAKERS = int(os.environ.get("MIN_SPEAKERS", 5))
MAX_SPEAKERS = int(os.environ.get("MAX_SPEAKERS", 18))
MODELS_DIR = os.environ.get("MODELS_DIR", "models")
CPU_THREADS = int(os.environ.get("CPU_THREADS", 0))

if CPU_THREADS > 0:
    torch.set_num_threads(CPU_THREADS)

TEXT = "text"
SPEAKER = "speaker"
DEVICE = "cpu"
BATCH_SIZE = 1
COMPUTE_TYPE = "int8"


def transcription(meeting_name: str):
    audio_file = f"audio/{meeting_name}.wav"

    os.makedirs(MODELS_DIR, exist_ok=True)

    model = whisperx.load_model(
        "large-v2",
        DEVICE,
        compute_type=COMPUTE_TYPE,
        language="en",
        download_root=MODELS_DIR,
    )

    audio = whisperx.load_audio(audio_file)
    result = model.transcribe(audio, batch_size=BATCH_SIZE)

    del model; gc.collect()

    logger.info("Aligning whisper output")
    model_a, metadata = whisperx.load_align_model(language_code=result["language"], device=DEVICE)
    result = whisperx.align(result["segments"], model_a, metadata, audio, DEVICE, return_char_alignments=False)

    del model_a; gc.collect()

    logger.info("Assigning speaker labels")
    diarize_model = DiarizationPipeline(token=HF_TOKEN, device=DEVICE)

    diarize_segments, speaker_embeddings = diarize_model(
        audio,
        min_speakers=MIN_SPEAKERS,
        max_speakers=MAX_SPEAKERS,
        return_embeddings=True,
    )

    result = whisperx.assign_word_speakers(diarize_segments, result)

    new_speaker_ids = None
    if speaker_embeddings:
        if not os.path.exists(Identifier.DB_PATH):
            logger.info("Generating speaker database")
            Identifier.save_db(speaker_embeddings)
        else:
            logger.info("Matching identifying existing speakers")
            identifier = Identifier()
            new_speaker_ids = identifier(speaker_embeddings)

    for segment in result["segments"]:
        segment.pop("words", None)

        if new_speaker_ids:
            if SPEAKER not in segment:
                segment[SPEAKER] = Identifier.DEFAULT_SPEAKER
                continue
            old_speaker_id = segment[SPEAKER]
            old_speaker_idx = int(old_speaker_id.split("_")[1])
            segment[SPEAKER] = new_speaker_ids[old_speaker_idx]

    logger.info("Saving to database")
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        save_meeting(conn, meeting_name, result["segments"])


if __name__ == "__main__":
    import sys
    transcription(sys.argv[1])
```

- [ ] **Step 6: Update transcription-service/Dockerfile to copy db.py**

```dockerfile
FROM ubuntu:24.04

RUN apt update && apt install -y ffmpeg

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

COPY transcription-service/pyproject.toml .
RUN uv sync --no-dev

COPY transcription-service/main.py transcription-service/transcription.py \
     transcription-service/identification.py transcription-service/db.py .
COPY monitoring.py log_config.json .

CMD ["uv", "run", "python", "main.py"]
```

- [ ] **Step 7: Commit**

```bash
git add transcription-service/db.py transcription-service/transcription.py transcription-service/Dockerfile tests/test_transcription_db.py transcription-service/pyproject.toml
git commit -m "feat: write transcription output to postgres instead of CSV"
```

---

## Task 5: Webapp transcript read (TDD)

**Files:**
- Modify: `conftest.py`
- Create: `webapp/lib/db.py`
- Modify: `webapp/main.py`
- Create: `tests/test_webapp_db.py`

- [ ] **Step 1: Add webapp to conftest.py sys.path**

Append to `conftest.py`:

```python
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "webapp"))
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_webapp_db.py`:

```python
import pytest
from unittest.mock import MagicMock


def test_get_transcript_returns_rows():
    mock_cur = MagicMock()
    mock_cur.fetchall.return_value = [
        (0, 0.0, 2.0, "Hello", "SPEAKER_00"),
        (1, 2.5, 4.0, "World", "SPEAKER_01"),
    ]
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

    from lib.db import get_transcript
    result = get_transcript(mock_conn, "Test Meeting")

    sql = mock_cur.execute.call_args.args[0]
    assert "WHERE meeting_name" in sql

    assert result == [
        {"id": 0, "start": 0.0, "end": 2.0, "text": "Hello", "speaker": "SPEAKER_00"},
        {"id": 1, "start": 2.5, "end": 4.0, "text": "World", "speaker": "SPEAKER_01"},
    ]


def test_get_transcript_empty_returns_empty_list():
    mock_cur = MagicMock()
    mock_cur.fetchall.return_value = []
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

    from lib.db import get_transcript
    result = get_transcript(mock_conn, "Missing Meeting")
    assert result == []
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
uv run pytest tests/test_webapp_db.py -v
```

Expected: `ModuleNotFoundError: No module named 'lib.db'`.

- [ ] **Step 4: Create webapp/lib/db.py**

```python
import os
import psycopg


def connect():
    return psycopg.connect(os.environ["DATABASE_URL"])


def get_transcript(conn, meeting_name: str) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT segment_index, start_time, end_time, text, speaker
            FROM utterances
            WHERE meeting_name = %s
            ORDER BY segment_index
            """,
            (meeting_name,),
        )
        rows = cur.fetchall()
    return [
        {"id": row[0], "start": row[1], "end": row[2], "text": row[3], "speaker": row[4]}
        for row in rows
    ]
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
uv run pytest tests/test_webapp_db.py -v
```

Expected: both tests PASS.

- [ ] **Step 6: Replace webapp/main.py**

```python
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse

import os
from lib.db import connect, get_transcript as db_get_transcript
from lib.search import do_search
from monitoring import setup_logging
from pathlib import Path
from contextlib import asynccontextmanager

logger = setup_logging("webapp")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Startup; initializing resources.")

    with connect() as conn:
        conn.execute("SELECT 1")  # raises on connection failure, preventing startup
    logger.info("Database connection verified.")

    global VIDEO_DB
    files = os.listdir(os.environ["DATA_DIR"] + "/videos")
    VIDEO_DB = [
        {"video_id": i, "name": f.replace(".mp4", "")}
        for i, f in enumerate(files)
    ]

    yield


app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount(
    "/assets",
    StaticFiles(directory="./frontend/dist/assets"),
    name="static"
)

VIDEO_DB = list()


@app.get("/")
def root():
    return FileResponse("./frontend/dist/index.html")


@app.get("/api/transcript/{video_id}")
def get_transcript(video_id: int):
    name = VIDEO_DB[video_id]["name"]
    with connect() as conn:
        rows = db_get_transcript(conn, name)
    if not rows:
        raise HTTPException(404)
    return rows


@app.get("/api/video/{video_id}")
def get_video(video_id: int, request: Request):
    path = os.environ['DATA_DIR'] + "/videos/" + VIDEO_DB[video_id]["name"] + ".mp4"

    video_path = Path(path)
    if not video_path.exists:
        raise HTTPException(404)

    file_size = video_path.stat().st_size
    range_header = request.headers.get("range")

    if range_header:
        start, end = range_header.replace("bytes=", "").split("-")
        start = int(start)
        end = int(end) if end else file_size - 1
    else:
        start, end = 0, file_size - 1

    def iterfile():
        with open(path, "rb") as f:
            f.seek(start)
            yield f.read(end - start + 1)

    headers = {
        "Content-Range": f"bytes {start}-{end}/{file_size}",
        "Accept-Ranges": "bytes",
        "Content-Length": str(end - start + 1),
    }

    return StreamingResponse(
        iterfile(),
        status_code=206 if range_header else 200,
        headers=headers,
        media_type="video/mp4",
    )


@app.get("/api/videos")
def get_videos():
    return VIDEO_DB


@app.get("/about")
def about():
    return FileResponse("./frontend/dist/index.html")


@app.get("/api/search")
def search(query: str):
    return do_search(query)


@app.get("/{full_path:path}")
def serve_frontend(full_path: str):
    return FileResponse("./frontend/dist/index.html")
```

- [ ] **Step 7: Commit**

```bash
git add webapp/lib/db.py webapp/main.py conftest.py tests/test_webapp_db.py webapp/pyproject.toml
git commit -m "feat: read transcripts from postgres in webapp"
```

---

## Task 6: Webapp search (TDD)

**Files:**
- Modify: `webapp/lib/search.py`
- Modify: `tests/test_webapp_db.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_webapp_db.py`:

```python
def test_do_search_returns_results(mocker):
    mock_cur = MagicMock()
    mock_cur.fetchall.return_value = [
        ("City Council 1-12-26", 10.0, "Traffic on Main Street", "SPEAKER_00", 0.91),
        ("City Council 1-26-26", 45.2, "The traffic light proposal", "SPEAKER_01", 0.87),
    ]
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)

    mock_embed_resp = MagicMock()
    mock_embed_resp.json.return_value = {"embeddings": [[0.1] * 384]}
    mocker.patch("lib.search.requests.post", return_value=mock_embed_resp)
    mocker.patch("lib.search.psycopg.connect", return_value=mock_conn)

    from lib.search import do_search
    results = do_search("traffic")

    assert len(results) == 2
    assert results[0]["meeting_name"] == "City Council 1-12-26"
    assert results[0]["start"] == 10.0
    assert results[0]["score"] == pytest.approx(0.91)

    sql = mock_cur.execute.call_args.args[0]
    assert "utterance_embeddings" in sql
    assert "ORDER BY" in sql
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_webapp_db.py::test_do_search_returns_results -v
```

Expected: test fails because `do_search` returns the current stub result, not DB rows.

- [ ] **Step 3: Replace webapp/lib/search.py**

```python
import os
import psycopg
import requests

EMBEDDINGS_SERVICE_URL = os.environ.get("EMBEDDINGS_SERVICE_URL", "http://embeddings-service:8001")


def do_search(query: str) -> list:
    resp = requests.post(
        f"{EMBEDDINGS_SERVICE_URL}/embeddings",
        json={"sentences": [query]},
        timeout=30,
    )
    resp.raise_for_status()
    query_embedding = resp.json()["embeddings"][0]
    vec_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT u.meeting_name, u.start_time, u.text, u.speaker,
                       1 - (ue.embedding <=> %s::vector) AS score
                FROM utterance_embeddings ue
                JOIN utterances u ON ue.utterance_id = u.id
                ORDER BY ue.embedding <=> %s::vector
                LIMIT 10
                """,
                (vec_str, vec_str),
            )
            rows = cur.fetchall()

    return [
        {
            "meeting_name": row[0],
            "start": row[1],
            "text": row[2],
            "speaker": row[3],
            "score": float(row[4]),
        }
        for row in rows
    ]
```

- [ ] **Step 4: Run all webapp tests to verify they pass**

```bash
uv run pytest tests/test_webapp_db.py -v
```

Expected: all 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add webapp/lib/search.py tests/test_webapp_db.py
git commit -m "feat: implement vector search in webapp"
```

---

## Task 7: Migration script (TDD)

**Files:**
- Create: `migrate_csv_to_db.py`
- Create: `tests/test_migration.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_migration.py`:

```python
import csv
from pathlib import Path
from unittest.mock import MagicMock


def test_migrate_single_csv(mocker, tmp_path):
    csv_file = tmp_path / "City Council 1-1-26.csv"
    with open(csv_file, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "start", "end", "text", "speaker"])
        writer.writeheader()
        writer.writerow({"id": 0, "start": 0.0, "end": 1.5, "text": "Hello", "speaker": "SPEAKER_00"})
        writer.writerow({"id": 1, "start": 2.0, "end": 3.0, "text": "World", "speaker": "SPEAKER_01"})

    mock_cur = MagicMock()
    mock_cur.fetchone.return_value = (0,)       # no existing rows for this meeting
    mock_cur.fetchall.return_value = [(1,), (2,)]
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)

    mock_resp = MagicMock()
    mock_resp.json.return_value = {"embeddings": [[0.1] * 384, [0.2] * 384]}
    mocker.patch("migrate_csv_to_db.requests.post", return_value=mock_resp)
    mocker.patch("migrate_csv_to_db.psycopg.connect", return_value=mock_conn)

    import migrate_csv_to_db
    migrate_csv_to_db.migrate_directory(str(tmp_path))

    mock_cur.executemany.assert_called_once()
    _, rows = mock_cur.executemany.call_args.args
    assert len(rows) == 2
    assert rows[0][0] == "City Council 1-1-26"  # meeting_name
    assert rows[0][4] == "Hello"                 # text


def test_migrate_skips_meetings_already_in_db(mocker, tmp_path):
    csv_file = tmp_path / "City Council 1-1-26.csv"
    with open(csv_file, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "start", "end", "text", "speaker"])
        writer.writeheader()
        writer.writerow({"id": 0, "start": 0.0, "end": 1.5, "text": "Hello", "speaker": "SPEAKER_00"})

    mock_cur = MagicMock()
    mock_cur.fetchone.return_value = (3,)       # 3 rows already exist — skip
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)

    mocker.patch("migrate_csv_to_db.psycopg.connect", return_value=mock_conn)

    import migrate_csv_to_db
    migrate_csv_to_db.migrate_directory(str(tmp_path))

    mock_cur.executemany.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_migration.py -v
```

Expected: `ModuleNotFoundError: No module named 'migrate_csv_to_db'`.

- [ ] **Step 3: Create migrate_csv_to_db.py**

```python
import csv
import os
import sys
from pathlib import Path

import psycopg
import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "transcription-service"))
from db import build_window_text

EMBEDDINGS_SERVICE_URL = os.environ.get("EMBEDDINGS_SERVICE_URL", "http://localhost:8001")
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://waltham:waltham_dev@localhost:5432/waltham")


def migrate_directory(transcriptions_dir: str) -> None:
    csv_files = sorted(Path(transcriptions_dir).glob("*.csv"))
    if not csv_files:
        print("No CSV files found.")
        return

    with psycopg.connect(DATABASE_URL) as conn:
        for csv_path in csv_files:
            _migrate_meeting(conn, csv_path.stem, csv_path)


def _migrate_meeting(conn, meeting_name: str, csv_path: Path) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM utterances WHERE meeting_name = %s",
            (meeting_name,),
        )
        count = cur.fetchone()[0]

    if count > 0:
        print(f"Skipping {meeting_name} (already in DB)")
        return

    print(f"Migrating {meeting_name}...")

    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        segments = [
            {
                "start": float(row["start"]),
                "end": float(row["end"]),
                "text": row["text"],
                "speaker": row["speaker"],
            }
            for row in reader
        ]

    windowed_texts = [build_window_text(segments, i) for i in range(len(segments))]

    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO utterances (meeting_name, segment_index, start_time, end_time, text, speaker)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (meeting_name, segment_index) DO NOTHING
            """,
            [
                (meeting_name, i, seg["start"], seg["end"], seg["text"], seg["speaker"])
                for i, seg in enumerate(segments)
            ],
        )
        cur.execute(
            "SELECT id FROM utterances WHERE meeting_name = %s ORDER BY segment_index",
            (meeting_name,),
        )
        ids = [row[0] for row in cur.fetchall()]
    conn.commit()

    resp = requests.post(
        f"{EMBEDDINGS_SERVICE_URL}/embeddings",
        json={"sentences": windowed_texts},
        timeout=120,
    )
    resp.raise_for_status()
    embeddings = resp.json()["embeddings"]

    with conn.cursor() as cur:
        for uid, embedding in zip(ids, embeddings):
            vec_str = "[" + ",".join(str(x) for x in embedding) + "]"
            cur.execute(
                "INSERT INTO utterance_embeddings (utterance_id, embedding) VALUES (%s, %s::vector)"
                " ON CONFLICT DO NOTHING",
                (uid, vec_str),
            )
    conn.commit()
    print(f"  Done: {len(segments)} utterances")


if __name__ == "__main__":
    transcriptions_dir = sys.argv[1] if len(sys.argv) > 1 else "transcriptions"
    migrate_directory(transcriptions_dir)
```

- [ ] **Step 4: Run all tests to verify they pass**

```bash
uv run pytest -v
```

Expected: all tests PASS including the full existing suite.

- [ ] **Step 5: Commit**

```bash
git add migrate_csv_to_db.py tests/test_migration.py
git commit -m "feat: add CSV migration script"
```

---

## Running the migration

After completing all tasks, import the existing CSVs:

```bash
# Ensure the stack is up
docker compose up postgres embeddings-service -d

# Run the migration (uses localhost ports exposed by compose)
uv run python migrate_csv_to_db.py transcriptions
```

Expected output: one "Migrating …" line per CSV file, then "Done: N utterances". Verify with:

```bash
docker compose exec postgres psql -U waltham -d waltham -c "SELECT meeting_name, COUNT(*) FROM utterances GROUP BY meeting_name ORDER BY meeting_name;"
```
