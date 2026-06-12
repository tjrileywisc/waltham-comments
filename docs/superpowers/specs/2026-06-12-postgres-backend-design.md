# Postgres Backend Design

**Date:** 2026-06-12
**Branch:** add-db-backend
**Status:** Approved

## Overview

Replace the per-meeting CSV transcription files with a PostgreSQL database backed by the pgvector extension. Store transcription segments in an `utterances` table and their sentence embedding vectors in a companion `utterance_embeddings` table. Wire up the webapp's stub search endpoint to perform real cosine-similarity queries against the stored vectors.

The filesystem-based meeting list (scanning `videos/`) is unchanged.

---

## Schema

`init.sql` — mounted into the postgres container at `/docker-entrypoint-initdb.d/init.sql` so it runs automatically on first start.

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

- `vector(384)` matches the output dimension of `all-MiniLM-L6-v2`
- HNSW index is chosen over IVFFlat because it requires no training phase and performs well at the expected dataset size
- `ON DELETE CASCADE` keeps the two tables in sync automatically

---

## Infrastructure changes

### New postgres service (`compose.yml`)

```yaml
postgres:
  image: pgvector/pgvector:pg17
  environment:
    POSTGRES_USER: ${POSTGRES_USER}
    POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    POSTGRES_DB: ${POSTGRES_DB}
  volumes:
    - postgres_data:/var/lib/postgresql/data
    - ./init.sql:/docker-entrypoint-initdb.d/init.sql

volumes:
  postgres_data:
```

### New environment variables (`.env`)

```
POSTGRES_USER=waltham
POSTGRES_PASSWORD=<secret>
POSTGRES_DB=waltham
DATABASE_URL=postgresql://waltham:<secret>@postgres:5432/waltham
```

`DATABASE_URL` is injected into the `transcription-service` and `web` containers. The embeddings service does not touch the database.

### New dependencies

- `transcription-service/pyproject.toml`: add `psycopg[binary]`
- `webapp/pyproject.toml`: add `psycopg[binary]`

---

## Write path (transcription service)

After WhisperX finishes and speaker identification is complete, instead of writing a CSV the service will:

1. **Batch INSERT** all segments into `utterances` in a single transaction.
2. **Build windowed texts** for each segment: concatenate the text of all preceding segments where `start_time >= current.end_time - 5.0`, then append the current segment's text. If the segment itself spans ≥ 5 seconds, use its text alone.
3. **Single HTTP POST** to `http://embeddings-service:8001/embeddings` with the full list of windowed texts (the endpoint already accepts a list).
4. **Batch INSERT** the returned vectors into `utterance_embeddings`.

Steps 1 and 4 run inside the same transaction so the two tables are never partially populated for a meeting.

`EMBEDDINGS_SERVICE_URL` (defaulting to `http://embeddings-service:8001`) is read from the environment to allow local overrides.

---

## Read path (webapp)

`GET /api/transcript/{video_id}` currently opens a CSV by meeting name. It will instead query:

```sql
SELECT segment_index, start_time, end_time, text, speaker
FROM utterances
WHERE meeting_name = $1
ORDER BY segment_index;
```

The JSON response shape is unchanged — the frontend consumes the same fields.

If no rows are found for the meeting name, return HTTP 404 (same behaviour as the current missing-file case).

---

## Search path (webapp)

`GET /api/search?query=<q>` — replaces the current stub in `webapp/lib/search.py`:

1. POST `{"sentences": [query]}` to `http://embeddings-service:8001/embeddings` to obtain a single query vector.
2. Run a pgvector cosine-similarity query:

```sql
SELECT u.meeting_name, u.start_time, u.text, u.speaker,
       1 - (ue.embedding <=> $1) AS score
FROM utterance_embeddings ue
JOIN utterances u ON ue.utterance_id = u.id
ORDER BY ue.embedding <=> $1
LIMIT 10;
```

`1 - cosine_distance` gives a similarity score in [0, 1]. Results are returned in descending similarity order.

`EMBEDDINGS_SERVICE_URL` is read from the environment (same variable as above, default `http://embeddings-service:8001`).

---

## Migration of existing data

Existing CSV files in `transcriptions/` will be imported by a one-time script (`migrate_csv_to_db.py` at the project root). It:

1. Reads every `*.csv` file from the `transcriptions/` directory.
2. Inserts rows into `utterances`.
3. Builds the same rolling-window texts as the write path.
4. Calls the embeddings service to generate vectors.
5. Inserts into `utterance_embeddings`.

The script is run manually (outside Docker) after the postgres container is up. CSV files are not deleted automatically — the operator removes them once migration is confirmed.

---

## Error handling

- **DB connection failure at startup (webapp):** the FastAPI lifespan hook attempts a connection; if it fails the app exits with a logged error rather than starting in a degraded state.
- **Embeddings service unreachable (transcription service):** logged as an error; the utterances are committed to the DB but the meeting is flagged with no embeddings. Embeddings can be back-filled by re-running the migration script against the already-inserted utterances.
- **Duplicate meeting:** the `UNIQUE (meeting_name, segment_index)` constraint prevents double-processing; the transcription service catches the conflict and logs a warning rather than crashing.

---

## Testing

- Existing unit tests are unaffected (they don't touch the webapp or transcription write path directly).
- New tests added for:
  - Rolling-window text builder (pure function, no DB needed)
  - `do_search()` with a mock psycopg connection
  - `GET /api/transcript/{video_id}` with a mock DB returning known rows
  - Migration script with a small fixture CSV
