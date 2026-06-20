# Speaker Labeling Interface Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an admin labeling interface to assign speaker names to diarization clusters, replacing the pickle-based embedding store with PostgreSQL and surfacing per-utterance identification confidence scores.

**Architecture:** Six sequential tasks — DB schema first, then transcription service (identification rewrite, DB layer, pipeline wiring), then admin HTTP API, then React frontend. Each task is independently testable and ends with a commit.

**Tech Stack:** Python 3.13, psycopg3, pgvector, FastAPI HTTPBasic auth, React 19, Vite, pytest, uv.

## Global Constraints

- Package manager: `uv` — never `pip` or `requirements.txt`
- Run tests: `uv run pytest`
- Logger: `monitoring.setup_logging(name)` only — never `logging.basicConfig()` or root logger
- Auth: `secrets.compare_digest` for all credential comparisons
- No retroactive re-identification; labeling is forward-only
- `react-router-dom` is already installed; `BrowserRouter` already wraps the app in `index.tsx`
- Spec: `docs/superpowers/specs/2026-06-16-speaker-labeling-design.md`
- `conftest.py` at repo root adds `transcription-service` and `webapp` to `sys.path` — tests import modules directly (e.g. `from identification import Identifier`, `from main import app`)

---

### Task 1: DB migration — speaker_embeddings table and utterance columns

**Files:**
- Create: `migrations/0006_speaker_embeddings.sql`

**Interfaces:**
- Produces:
  - `utterances.diarization_speaker TEXT` — original WhisperX cluster label (e.g. `"SPEAKER_0"`)
  - `utterances.confidence FLOAT` — cosine similarity score at identification time; NULL if unmatched or pre-feature
  - `speaker_embeddings` table: `(id, speaker_id REFERENCES speakers, meeting_id REFERENCES meetings NOT NULL, diarization_speaker TEXT NOT NULL, embedding vector(256), is_canonical BOOL NOT NULL DEFAULT FALSE, created_at TIMESTAMP NOT NULL DEFAULT NOW())` with `UNIQUE(meeting_id, diarization_speaker)`

- [ ] **Step 1: Create the migration file**

`migrations/0006_speaker_embeddings.sql`:
```sql
ALTER TABLE utterances ADD COLUMN diarization_speaker TEXT;
ALTER TABLE utterances ADD COLUMN confidence FLOAT;

CREATE TABLE speaker_embeddings (
    id                   SERIAL PRIMARY KEY,
    speaker_id           INT REFERENCES speakers(id),
    meeting_id           INT REFERENCES meetings(id) NOT NULL,
    diarization_speaker  TEXT NOT NULL,
    embedding            vector(256),
    is_canonical         BOOL NOT NULL DEFAULT FALSE,
    created_at           TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (meeting_id, diarization_speaker)
);
```

- [ ] **Step 2: Apply the migration**

The webapp applies yoyo migrations on startup. Start it to apply:
```bash
docker compose up webapp --build
```

Or apply directly with a local DB connection:
```bash
DATABASE_URL=postgresql://user:pass@localhost/dbname uv run python -c "
from yoyo import get_backend, read_migrations
import os
url = os.environ['DATABASE_URL'].replace('postgresql://', 'postgresql+psycopg://', 1)
backend = get_backend(url)
migrations = read_migrations('./migrations')
with backend.lock():
    backend.apply_migrations(backend.to_apply(migrations))
print('done')
"
```

- [ ] **Step 3: Verify migration applied**

```bash
DATABASE_URL=postgresql://user:pass@localhost/dbname uv run python -c "
import psycopg, os
conn = psycopg.connect(os.environ['DATABASE_URL'])
cur = conn.cursor()
cur.execute(\"SELECT column_name FROM information_schema.columns WHERE table_name='utterances' AND column_name IN ('diarization_speaker','confidence')\")
cols = [r[0] for r in cur.fetchall()]
assert 'diarization_speaker' in cols and 'confidence' in cols, f'Missing columns: {cols}'
cur.execute(\"SELECT table_name FROM information_schema.tables WHERE table_name='speaker_embeddings'\")
assert cur.fetchone(), 'speaker_embeddings table missing'
print('Migration OK')
"
```
Expected output: `Migration OK`

- [ ] **Step 4: Commit**

```bash
git add migrations/0006_speaker_embeddings.sql
git commit -m "feat: add speaker_embeddings table and diarization_speaker/confidence columns on utterances"
```

---

### Task 2: Rewrite identification.py — DB-backed with confidence scores

**Files:**
- Modify: `transcription-service/identification.py`
- Modify: `tests/test_identification.py` (replace existing tests; old interface is gone)

**Interfaces:**
- Produces:
  - `Identifier()(conn, speaker_embeddings: Dict[str, NDArray]) -> List[tuple[str, float | None]]`
    — one `(speaker_name, confidence)` per input cluster, in the same order as `speaker_embeddings.items()`; unmatched clusters return `("DEFAULT", None)`
  - `Identifier.DEFAULT_SPEAKER = "DEFAULT"`
  - `Identifier.SIMILARITY_THRESHOLD = 0.7`
  - `conn` is a psycopg connection passed in by the caller; `Identifier` never opens its own connection

- [ ] **Step 1: Write the failing tests**

Replace the full contents of `tests/test_identification.py`:
```python
import numpy as np
import pytest
from unittest.mock import MagicMock
from identification import Identifier


def make_conn(rows):
    """Mock psycopg connection whose cursor returns `rows` from fetchall."""
    conn = MagicMock()
    cur = MagicMock()
    cur.__enter__ = lambda s: s
    cur.__exit__ = MagicMock(return_value=False)
    cur.fetchall.return_value = rows
    conn.cursor.return_value = cur
    return conn


def test_returns_default_when_no_canonical_embeddings():
    identifier = Identifier()
    result = identifier(make_conn([]), {"SPEAKER_0": np.array([1.0, 0.0])})
    assert result == [("DEFAULT", None)]


def test_matches_speaker_above_threshold():
    conn = make_conn([("Alice", "[1.0,0.0]")])
    identifier = Identifier()
    result = identifier(conn, {"SPEAKER_0": np.array([1.0, 0.0])})
    name, score = result[0]
    assert name == "Alice"
    assert score == pytest.approx(1.0)


def test_returns_default_when_below_threshold():
    conn = make_conn([("Alice", "[1.0,0.0]")])
    identifier = Identifier()
    result = identifier(conn, {"SPEAKER_0": np.array([0.0, 1.0])})
    name, score = result[0]
    assert name == "DEFAULT"
    assert score is None


def test_picks_best_match_among_multiple_speakers():
    conn = make_conn([("Alice", "[1.0,0.0]"), ("Bob", "[0.0,1.0]")])
    identifier = Identifier()
    result = identifier(conn, {"SPEAKER_0": np.array([0.9, 0.1])})
    name, score = result[0]
    assert name == "Alice"
    assert score > 0.7


def test_multiple_clusters_matched_independently():
    conn = make_conn([("Alice", "[1.0,0.0]"), ("Bob", "[0.0,1.0]")])
    identifier = Identifier()
    result = identifier(conn, {
        "SPEAKER_0": np.array([1.0, 0.0]),
        "SPEAKER_1": np.array([0.0, 1.0]),
    })
    assert result[0][0] == "Alice"
    assert result[1][0] == "Bob"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_identification.py -v
```
Expected: 5 failures/errors — old `Identifier` constructor takes a dict argument; new tests call `Identifier()` with no args.

- [ ] **Step 3: Rewrite identification.py**

Replace the full contents of `transcription-service/identification.py`:
```python
import numpy as np
from numpy.typing import NDArray
from typing import Dict, List
from sklearn.metrics.pairwise import cosine_similarity


class Identifier:
    SIMILARITY_THRESHOLD = 0.7
    DEFAULT_SPEAKER = "DEFAULT"

    def __call__(
        self,
        conn,
        speaker_embeddings: Dict[str, NDArray[np.float64]],
    ) -> List[tuple[str, float | None]]:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT s.speaker_name, se.embedding::text
                FROM speaker_embeddings se
                JOIN speakers s ON s.id = se.speaker_id
                WHERE se.is_canonical = TRUE
                """
            )
            rows = cur.fetchall()

        if not rows:
            return [(self.DEFAULT_SPEAKER, None)] * len(speaker_embeddings)

        db_names = [row[0] for row in rows]
        db_embeddings = np.array([
            [float(x) for x in row[1].strip("[]").split(",")]
            for row in rows
        ])

        incoming = np.array(list(speaker_embeddings.values()))
        results = cosine_similarity(incoming, db_embeddings)
        best_idx = np.argmax(results, axis=1)
        best_scores = results[np.arange(len(results)), best_idx]

        return [
            (db_names[best_idx[i]], float(best_scores[i]))
            if best_scores[i] >= self.SIMILARITY_THRESHOLD
            else (self.DEFAULT_SPEAKER, None)
            for i in range(len(speaker_embeddings))
        ]
```

- [ ] **Step 4: Run tests and verify they pass**

```bash
uv run pytest tests/test_identification.py -v
```
Expected: 5 PASSED

- [ ] **Step 5: Commit**

```bash
git add transcription-service/identification.py tests/test_identification.py
git commit -m "feat: replace pickle Identifier with DB-backed version; returns (name, confidence) pairs"
```

---

### Task 3: Update transcription-service/db.py — new columns and save_speaker_embeddings

**Files:**
- Modify: `transcription-service/db.py`
- Modify: `tests/test_transcription_db.py` (update two broken tests, add three new ones)

**Interfaces:**
- Consumes: same `conn`, `meeting_name`, `segments` as before; segments now also carry optional `diarization_speaker: str` and `confidence: float | None` keys
- Produces:
  - `save_meeting(conn, meeting_name, segments) -> tuple[int, dict[str, int]]` — returns `(meeting_id, speaker_name_to_id)` where `speaker_name_to_id` maps speaker name → DB `speakers.id`
  - `save_speaker_embeddings(conn, meeting_id: int, speaker_embeddings: Dict[str, NDArray], cluster_to_speaker_id: Dict[str, int | None]) -> None`

- [ ] **Step 1: Update the failing tests**

In `tests/test_transcription_db.py`, replace `test_save_meeting_inserts_utterances_and_embeddings` and `test_save_meeting_uses_default_speaker_when_missing`, and add three new tests. The full updated file (keep all existing tests for `build_window_text`, `is_meeting_processed`, `extract_*`; only the `save_meeting` tests change):

Replace `test_save_meeting_inserts_utterances_and_embeddings`:
```python
def test_save_meeting_returns_meeting_id_and_speaker_lookup(mocker):
    segments = [{"start": 0.0, "end": 2.0, "text": "Hello", "speaker": "DEFAULT"}]

    mock_cur = MagicMock()
    mock_cur.fetchone.return_value = (7,)          # meeting_id = 7
    mock_cur.fetchall.side_effect = [
        [(99, "DEFAULT")],                          # speaker lookup
        [(1,)],                                     # utterance ids
    ]
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

    mock_resp = MagicMock()
    mock_resp.json.return_value = {"embeddings": [[0.1] * 384]}
    mocker.patch("db.requests.post", return_value=mock_resp)

    meeting_id, speaker_lookup = save_meeting(mock_conn, "Test Meeting 1-1-26", segments)

    assert meeting_id == 7
    assert speaker_lookup["DEFAULT"] == 99
```

Replace `test_save_meeting_uses_default_speaker_when_missing`:
```python
def test_save_meeting_stores_diarization_speaker_and_confidence(mocker):
    segments = [{
        "start": 0.0, "end": 2.0, "text": "Hello",
        "speaker": "DEFAULT",
        "diarization_speaker": "SPEAKER_2",
        "confidence": 0.83,
    }]

    mock_cur = MagicMock()
    mock_cur.fetchone.return_value = (1,)
    mock_cur.fetchall.side_effect = [[(99, "DEFAULT")], [(1,)]]
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

    mock_resp = MagicMock()
    mock_resp.json.return_value = {"embeddings": [[0.0] * 384]}
    mocker.patch("db.requests.post", return_value=mock_resp)

    save_meeting(mock_conn, "Test Meeting 1-2-26", segments)

    sql, rows = mock_cur.executemany.call_args.args
    assert "diarization_speaker" in sql
    assert "confidence" in sql
    assert rows[0][6] == "SPEAKER_2"   # diarization_speaker at index 6
    assert rows[0][7] == pytest.approx(0.83)  # confidence at index 7
```

Add after the existing tests:
```python
def test_save_meeting_stores_none_for_missing_diarization_fields(mocker):
    segments = [{"start": 0.0, "end": 1.0, "text": "Hello", "speaker": "DEFAULT"}]

    mock_cur = MagicMock()
    mock_cur.fetchone.return_value = (1,)
    mock_cur.fetchall.side_effect = [[(99, "DEFAULT")], [(1,)]]
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

    mock_resp = MagicMock()
    mock_resp.json.return_value = {"embeddings": [[0.0] * 384]}
    mocker.patch("db.requests.post", return_value=mock_resp)

    save_meeting(mock_conn, "Test Meeting 1-3-26", segments)

    _, rows = mock_cur.executemany.call_args.args
    assert rows[0][6] is None   # diarization_speaker
    assert rows[0][7] is None   # confidence


def test_save_speaker_embeddings_inserts_one_row_per_cluster(mocker):
    import numpy as np
    from db import save_speaker_embeddings

    mock_cur = MagicMock()
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

    embeddings = {
        "SPEAKER_0": np.zeros(256),
        "SPEAKER_1": np.ones(256),
    }
    cluster_to_speaker_id = {"SPEAKER_0": 5, "SPEAKER_1": None}

    save_speaker_embeddings(mock_conn, meeting_id=3, speaker_embeddings=embeddings,
                            cluster_to_speaker_id=cluster_to_speaker_id)

    assert mock_cur.execute.call_count == 2
    first_call_args = mock_cur.execute.call_args_list[0].args
    assert "INSERT INTO speaker_embeddings" in first_call_args[0]


def test_save_speaker_embeddings_passes_none_speaker_id_for_unmatched(mocker):
    import numpy as np
    from db import save_speaker_embeddings

    mock_cur = MagicMock()
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

    embeddings = {"SPEAKER_0": np.zeros(256)}
    save_speaker_embeddings(mock_conn, meeting_id=1, speaker_embeddings=embeddings,
                            cluster_to_speaker_id={"SPEAKER_0": None})

    params = mock_cur.execute.call_args_list[0].args[1]
    assert params[0] is None   # speaker_id is None for unmatched cluster
    assert params[2] == "SPEAKER_0"
```

- [ ] **Step 2: Run tests to verify the two replaced tests fail**

```bash
uv run pytest tests/test_transcription_db.py::test_save_meeting_returns_meeting_id_and_speaker_lookup tests/test_transcription_db.py::test_save_meeting_stores_diarization_speaker_and_confidence -v
```
Expected: 2 FAILED — `save_meeting` still returns None; INSERT SQL missing new columns.

- [ ] **Step 3: Update save_meeting in transcription-service/db.py**

Replace the `save_meeting` function (keep all other functions unchanged):

```python
def save_meeting(conn, meeting_name: str, segments: list[dict]) -> tuple[int, dict[str, int]]:
    windowed_texts = [build_window_text(segments, i) for i in range(len(segments))]

    meeting_type = extract_meeting_type(meeting_name)
    meeting_date = extract_meeting_date(meeting_name)
    meeting_part = extract_meeting_part(meeting_name)

    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO meetings (meeting_name, meeting_type, meeting_date, meeting_part) VALUES (%s, %s, %s, %s) RETURNING id",
            (meeting_name, meeting_type, meeting_date, meeting_part),
        )
        meeting_id = cur.fetchone()[0]

        speakers = set([seg.get("speaker", "DEFAULT") for seg in segments])
        speakers.add("DEFAULT")
        cur.execute(
            "SELECT id, speaker_name FROM speakers WHERE speaker_name = ANY(%s)",
            (list(speakers),),
        )
        speaker_lookup = {sp: sp_id for sp_id, sp in cur.fetchall()}

        cur.executemany(
            """
            INSERT INTO utterances
                (meeting_id, segment_index, start_time, end_time, text, speaker_id, diarization_speaker, confidence)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (meeting_id, segment_index) DO NOTHING
            """,
            [
                (
                    meeting_id, i, seg["start"], seg["end"], seg["text"],
                    speaker_lookup.get(seg.get("speaker", "DEFAULT")) or speaker_lookup["DEFAULT"],
                    seg.get("diarization_speaker"),
                    seg.get("confidence"),
                )
                for i, seg in enumerate(segments)
            ],
        )

        cur.execute(
            "SELECT id FROM utterances WHERE meeting_id = %s ORDER BY segment_index",
            (meeting_id,),
        )
        ids = [row[0] for row in cur.fetchall()]

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
    return meeting_id, speaker_lookup
```

- [ ] **Step 4: Add save_speaker_embeddings to transcription-service/db.py**

Append to the end of `transcription-service/db.py`:

```python
def save_speaker_embeddings(
    conn,
    meeting_id: int,
    speaker_embeddings: dict,
    cluster_to_speaker_id: dict[str, int | None],
) -> None:
    with conn.cursor() as cur:
        for cluster_id, embedding in speaker_embeddings.items():
            vec_str = "[" + ",".join(str(x) for x in embedding) + "]"
            cur.execute(
                """
                INSERT INTO speaker_embeddings (speaker_id, meeting_id, diarization_speaker, embedding)
                VALUES (%s, %s, %s, %s::vector)
                ON CONFLICT (meeting_id, diarization_speaker) DO NOTHING
                """,
                (cluster_to_speaker_id.get(cluster_id), meeting_id, cluster_id, vec_str),
            )
    conn.commit()
```

- [ ] **Step 5: Run all db tests and verify they pass**

```bash
uv run pytest tests/test_transcription_db.py -v
```
Expected: all tests pass (existing `build_window_text`, `extract_*`, `is_meeting_processed` tests unchanged; two replaced `save_meeting` tests now pass; three new tests pass).

- [ ] **Step 6: Commit**

```bash
git add transcription-service/db.py tests/test_transcription_db.py
git commit -m "feat: update save_meeting to store diarization_speaker and confidence; add save_speaker_embeddings"
```

---

### Task 4: Update transcription.py — wire new identification into pipeline

**Files:**
- Modify: `transcription-service/transcription.py`

No new test file for this task — the pipeline integration requires a live WhisperX run to verify. Unit behaviour is covered by Tasks 2 and 3.

**Interfaces:**
- Consumes:
  - `Identifier()(conn, speaker_embeddings) -> List[tuple[str, float | None]]` (Task 2)
  - `save_meeting(conn, meeting_name, segments) -> tuple[int, dict[str, int]]` (Task 3)
  - `save_speaker_embeddings(conn, meeting_id, speaker_embeddings, cluster_to_speaker_id)` (Task 3)
- Produces: side effects only — utterances stored with `diarization_speaker` and `confidence` populated; `speaker_embeddings` rows written per meeting; first-meeting behaviour: no auto-seeding, all clusters stored with `speaker_id = NULL`

- [ ] **Step 1: Replace transcription.py with the updated version**

Replace the full contents of `transcription-service/transcription.py`:

```python
import gc
import os
import psycopg

from identification import Identifier
from db import save_meeting, is_meeting_processed, save_speaker_embeddings

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

    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        if is_meeting_processed(conn, meeting_name):
            logger.info(f"skipping {meeting_name}, already in database")
            return

    audio_file = f"audio/{meeting_name}.wav"
    os.makedirs(MODELS_DIR, exist_ok=True)

    model = whisperx.load_model(
        "large-v2", DEVICE,
        compute_type=COMPUTE_TYPE, language="en",
        download_root=MODELS_DIR, threads=8,
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

    cluster_ids = list(speaker_embeddings.keys()) if speaker_embeddings else []

    for segment in result["segments"]:
        segment.pop("words", None)
        segment["diarization_speaker"] = segment.get(SPEAKER, Identifier.DEFAULT_SPEAKER)

    logger.info("Saving to database")
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        identification_results: list[tuple[str, float | None]] = []
        if speaker_embeddings:
            logger.info("Identifying speakers")
            identification_results = Identifier()(conn, speaker_embeddings)

        for segment in result["segments"]:
            orig = segment.get("diarization_speaker", Identifier.DEFAULT_SPEAKER)
            if identification_results and orig != Identifier.DEFAULT_SPEAKER:
                try:
                    idx = int(orig.split("_")[1])
                    name, confidence = identification_results[idx]
                except (ValueError, IndexError):
                    name, confidence = Identifier.DEFAULT_SPEAKER, None
                segment[SPEAKER] = name
                segment["confidence"] = confidence
            else:
                segment[SPEAKER] = Identifier.DEFAULT_SPEAKER
                segment["confidence"] = None

        meeting_id, speaker_name_to_id = save_meeting(conn, meeting_name, result["segments"])

        if speaker_embeddings and identification_results:
            cluster_to_speaker_id = {
                cid: (speaker_name_to_id.get(name) if name != Identifier.DEFAULT_SPEAKER else None)
                for cid, (name, _) in zip(cluster_ids, identification_results)
            }
            save_speaker_embeddings(conn, meeting_id, speaker_embeddings, cluster_to_speaker_id)


if __name__ == "__main__":
    import sys
    transcription(sys.argv[1])
```

- [ ] **Step 2: Commit**

```bash
git add transcription-service/transcription.py
git commit -m "feat: wire new identification and speaker_embeddings into transcription pipeline"
```

---

### Task 5: Admin API backend

**Files:**
- Create: `webapp/lib/admin.py`
- Modify: `webapp/main.py`
- Create: `tests/test_admin_api.py`

**Interfaces:**
- Produces (all routes require HTTP Basic Auth from `ADMIN_USER`/`ADMIN_PASSWORD` env vars):
  - `GET /admin/meetings` → `[{id, meeting_name, meeting_date, meeting_type, unlabeled_count}]`
  - `GET /admin/meetings/{id}/clusters` → `[{embedding_id, diarization_speaker, speaker_name, is_canonical, utterances: [{id, start, end, text, confidence}]}]`
  - `POST /admin/meetings/{id}/clusters/{cluster}/label` body `{speaker_name: str}` → `{ok: true}`
  - `POST /admin/speaker-embeddings/{embedding_id}/canonical` → `{ok: true}`
  - `GET /admin/speakers` → `[{id, speaker_name, speaker_role, canonical_embedding_id, utterance_count, mean_confidence, low_confidence_count}]`
  - All routes return 401 without valid credentials; 503 if `ADMIN_USER`/`ADMIN_PASSWORD` are unset

- [ ] **Step 1: Create webapp/lib/admin.py**

`webapp/lib/admin.py`:
```python
import os
import secrets
from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import HTTPBasic, HTTPBasicCredentials

security = HTTPBasic()


def get_admin(credentials: Annotated[HTTPBasicCredentials, Depends(security)]):
    admin_user = os.environ.get("ADMIN_USER", "")
    admin_password = os.environ.get("ADMIN_PASSWORD", "")
    if not admin_user or not admin_password:
        raise HTTPException(status_code=503, detail="Admin credentials not configured")
    ok = (
        secrets.compare_digest(credentials.username, admin_user)
        and secrets.compare_digest(credentials.password, admin_password)
    )
    if not ok:
        raise HTTPException(status_code=401, headers={"WWW-Authenticate": "Basic"})


def get_meetings(conn) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT m.id, m.meeting_name, m.meeting_date, m.meeting_type,
                   COUNT(se.id) FILTER (WHERE se.speaker_id IS NULL) AS unlabeled_count
            FROM meetings m
            LEFT JOIN speaker_embeddings se ON se.meeting_id = m.id
            GROUP BY m.id
            ORDER BY m.meeting_date DESC
            """
        )
        rows = cur.fetchall()
    return [
        {
            "id": r[0],
            "meeting_name": r[1],
            "meeting_date": str(r[2]),
            "meeting_type": r[3],
            "unlabeled_count": r[4] or 0,
        }
        for r in rows
    ]


def get_clusters(conn, meeting_id: int) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT se.id, se.diarization_speaker, se.is_canonical, s.speaker_name
            FROM speaker_embeddings se
            LEFT JOIN speakers s ON s.id = se.speaker_id
            WHERE se.meeting_id = %s
            ORDER BY se.diarization_speaker
            """,
            (meeting_id,),
        )
        clusters = cur.fetchall()

        result = []
        for se_id, disp_speaker, is_canonical, speaker_name in clusters:
            cur.execute(
                """
                SELECT u.id, u.start_time, u.end_time, u.text, u.confidence
                FROM utterances u
                WHERE u.meeting_id = %s AND u.diarization_speaker = %s
                ORDER BY u.segment_index
                LIMIT 50
                """,
                (meeting_id, disp_speaker),
            )
            utterances = [
                {
                    "id": row[0],
                    "start": float(row[1]),
                    "end": float(row[2]),
                    "text": row[3],
                    "confidence": float(row[4]) if row[4] is not None else None,
                }
                for row in cur.fetchall()
            ]
            result.append(
                {
                    "embedding_id": se_id,
                    "diarization_speaker": disp_speaker,
                    "speaker_name": speaker_name,
                    "is_canonical": is_canonical,
                    "utterances": utterances,
                }
            )
    return result


def label_cluster(conn, meeting_id: int, diarization_speaker: str, speaker_name: str) -> None:
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM speakers WHERE speaker_name = %s", (speaker_name,))
        row = cur.fetchone()
        if row:
            speaker_id = row[0]
        else:
            cur.execute(
                "INSERT INTO speakers (speaker_name) VALUES (%s) RETURNING id",
                (speaker_name,),
            )
            speaker_id = cur.fetchone()[0]

        cur.execute(
            "UPDATE utterances SET speaker_id = %s WHERE meeting_id = %s AND diarization_speaker = %s",
            (speaker_id, meeting_id, diarization_speaker),
        )
        cur.execute(
            "UPDATE speaker_embeddings SET speaker_id = %s WHERE meeting_id = %s AND diarization_speaker = %s",
            (speaker_id, meeting_id, diarization_speaker),
        )
    conn.commit()


def set_canonical(conn, embedding_id: int) -> None:
    with conn.cursor() as cur:
        cur.execute("SELECT speaker_id FROM speaker_embeddings WHERE id = %s", (embedding_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Embedding not found")
        if row[0] is None:
            raise HTTPException(
                status_code=400, detail="Label this cluster first before marking it canonical"
            )
        speaker_id = row[0]
        cur.execute(
            "UPDATE speaker_embeddings SET is_canonical = FALSE WHERE speaker_id = %s",
            (speaker_id,),
        )
        cur.execute(
            "UPDATE speaker_embeddings SET is_canonical = TRUE WHERE id = %s",
            (embedding_id,),
        )
    conn.commit()


def get_speakers(conn) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                s.id, s.speaker_name, s.speaker_role,
                se_c.id AS canonical_embedding_id,
                COUNT(u.id) AS utterance_count,
                AVG(u.confidence) AS mean_confidence,
                COUNT(u.id) FILTER (WHERE u.confidence IS NOT NULL AND u.confidence < 0.7) AS low_confidence_count
            FROM speakers s
            LEFT JOIN speaker_embeddings se_c
                ON se_c.speaker_id = s.id AND se_c.is_canonical = TRUE
            LEFT JOIN utterances u ON u.speaker_id = s.id
            WHERE s.speaker_name != 'DEFAULT'
            GROUP BY s.id, se_c.id
            ORDER BY s.speaker_name
            """
        )
        rows = cur.fetchall()
    return [
        {
            "id": r[0],
            "speaker_name": r[1],
            "speaker_role": r[2],
            "canonical_embedding_id": r[3],
            "utterance_count": r[4],
            "mean_confidence": float(r[5]) if r[5] is not None else None,
            "low_confidence_count": r[6],
        }
        for r in rows
    ]
```

- [ ] **Step 2: Write the failing tests**

`tests/test_admin_api.py`:
```python
import os
import pytest
from unittest.mock import MagicMock, patch

os.environ.setdefault("ADMIN_USER", "admin")
os.environ.setdefault("ADMIN_PASSWORD", "secret")
os.environ.setdefault("DATABASE_URL", "postgresql://test")
os.environ.setdefault("DATA_DIR", "/tmp")

from fastapi.testclient import TestClient
from main import app

client = TestClient(app, raise_server_exceptions=False)
AUTH = ("admin", "secret")


def make_mock_conn(fetchall_results=None, fetchone_results=None):
    mock_cur = MagicMock()
    mock_cur.__enter__ = lambda s: s
    mock_cur.__exit__ = MagicMock(return_value=False)
    if fetchall_results is not None:
        mock_cur.fetchall.side_effect = fetchall_results
    if fetchone_results is not None:
        mock_cur.fetchone.side_effect = fetchone_results
    mock_conn = MagicMock()
    mock_conn.__enter__ = lambda s: mock_conn
    mock_conn.__exit__ = MagicMock(return_value=False)
    mock_conn.cursor.return_value = mock_cur
    return mock_conn


def test_admin_meetings_requires_auth():
    r = client.get("/admin/meetings")
    assert r.status_code == 401


def test_admin_meetings_rejects_wrong_password():
    r = client.get("/admin/meetings", auth=("admin", "wrong"))
    assert r.status_code == 401


def test_admin_meetings_returns_list():
    mock_conn = make_mock_conn(
        fetchall_results=[[(1, "City Council 1-12-26", "2026-01-12", "City Council", 2)]]
    )
    with patch("main.connect", return_value=mock_conn):
        r = client.get("/admin/meetings", auth=AUTH)
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["meeting_name"] == "City Council 1-12-26"
    assert data[0]["unlabeled_count"] == 2


def test_admin_label_cluster_returns_ok():
    mock_conn = make_mock_conn(
        fetchone_results=[None, (42,)],  # no existing speaker, then new id
    )
    with patch("main.connect", return_value=mock_conn):
        r = client.post(
            "/admin/meetings/1/clusters/SPEAKER_0/label",
            json={"speaker_name": "Councilor Smith"},
            auth=AUTH,
        )
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_admin_set_canonical_404_for_missing_embedding():
    mock_conn = make_mock_conn(fetchone_results=[None])
    with patch("main.connect", return_value=mock_conn):
        r = client.post("/admin/speaker-embeddings/999/canonical", auth=AUTH)
    assert r.status_code == 404


def test_admin_set_canonical_400_when_embedding_unlabeled():
    mock_conn = make_mock_conn(fetchone_results=[(None,)])  # speaker_id is NULL
    with patch("main.connect", return_value=mock_conn):
        r = client.post("/admin/speaker-embeddings/1/canonical", auth=AUTH)
    assert r.status_code == 400


def test_admin_speakers_returns_list():
    mock_conn = make_mock_conn(
        fetchall_results=[[(3, "Councilor Smith", None, 42, 100, 0.81, 5)]]
    )
    with patch("main.connect", return_value=mock_conn):
        r = client.get("/admin/speakers", auth=AUTH)
    assert r.status_code == 200
    data = r.json()
    assert data[0]["speaker_name"] == "Councilor Smith"
    assert data[0]["mean_confidence"] == pytest.approx(0.81)
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
uv run pytest tests/test_admin_api.py -v
```
Expected: failures — admin routes don't exist yet.

- [ ] **Step 4: Add admin routes to webapp/main.py**

At the top of `webapp/main.py`, update the existing FastAPI import line to add `Depends`:
```python
from fastapi import FastAPI, HTTPException, Request, Depends
```

Add this import after the existing `lib.db` import:
```python
from lib.admin import (
    get_admin, get_meetings, get_clusters,
    label_cluster, set_canonical, get_speakers,
)
```

Add this Pydantic model after the existing `SearchResult` model:
```python
class LabelRequest(BaseModel):
    speaker_name: str
```

Add the five admin route handlers before the final catch-all `/{full_path:path}` route:
```python
@app.get("/admin/meetings")
def admin_meetings(_=Depends(get_admin)):
    with connect() as conn:
        return get_meetings(conn)


@app.get("/admin/meetings/{meeting_id}/clusters")
def admin_meeting_clusters(meeting_id: int, _=Depends(get_admin)):
    with connect() as conn:
        return get_clusters(conn, meeting_id)


@app.post("/admin/meetings/{meeting_id}/clusters/{cluster}/label")
def admin_label_cluster(meeting_id: int, cluster: str, body: LabelRequest, _=Depends(get_admin)):
    with connect() as conn:
        label_cluster(conn, meeting_id, cluster, body.speaker_name)
    return {"ok": True}


@app.post("/admin/speaker-embeddings/{embedding_id}/canonical")
def admin_set_canonical(embedding_id: int, _=Depends(get_admin)):
    with connect() as conn:
        set_canonical(conn, embedding_id)
    return {"ok": True}


@app.get("/admin/speakers")
def admin_speakers(_=Depends(get_admin)):
    with connect() as conn:
        return get_speakers(conn)
```

- [ ] **Step 5: Run tests and verify they pass**

```bash
uv run pytest tests/test_admin_api.py -v
```
Expected: 7 PASSED

- [ ] **Step 6: Commit**

```bash
git add webapp/lib/admin.py webapp/main.py tests/test_admin_api.py
git commit -m "feat: add admin API endpoints with HTTP Basic Auth"
```

---

### Task 6: Admin frontend pages

**Files:**
- Create: `webapp/frontend/src/AdminMeetings.tsx`
- Create: `webapp/frontend/src/AdminLabel.tsx`
- Modify: `webapp/frontend/src/index.tsx`

**Interfaces:**
- Consumes: all five admin endpoints from Task 5; browser will prompt for Basic Auth credentials when hitting `/admin/*`
- Produces: navigable `/admin/meetings` and `/admin/meetings/:id/label` routes
- `react-router-dom` and `BrowserRouter` are already in place — no package changes needed

- [ ] **Step 1: Create AdminMeetings.tsx**

`webapp/frontend/src/AdminMeetings.tsx`:
```tsx
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

type Meeting = {
  id: number;
  meeting_name: string;
  meeting_date: string;
  meeting_type: string;
  unlabeled_count: number;
};

function AdminMeetings() {
  const [meetings, setMeetings] = useState<Meeting[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/admin/meetings")
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then(setMeetings)
      .catch((e: Error) => setError(e.message));
  }, []);

  if (error) return <p>Error: {error}</p>;

  return (
    <div>
      <h1>Speaker Labeling</h1>
      <table>
        <thead>
          <tr>
            <th>Date</th>
            <th>Name</th>
            <th>Type</th>
            <th>Unlabeled clusters</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {meetings.map((m) => (
            <tr key={m.id}>
              <td>{m.meeting_date}</td>
              <td>{m.meeting_name}</td>
              <td>{m.meeting_type}</td>
              <td>{m.unlabeled_count > 0 ? m.unlabeled_count : "—"}</td>
              <td>
                <Link to={`/admin/meetings/${m.id}/label`}>Label</Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default AdminMeetings;
```

- [ ] **Step 2: Create AdminLabel.tsx**

`webapp/frontend/src/AdminLabel.tsx`:
```tsx
import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import VideoPlayer from "./VideoPlayer";

type Utterance = {
  id: number;
  start: number;
  end: number;
  text: string;
  confidence: number | null;
};

type Cluster = {
  embedding_id: number;
  diarization_speaker: string;
  speaker_name: string | null;
  is_canonical: boolean;
  utterances: Utterance[];
};

type KnownSpeaker = { id: number; speaker_name: string };

function formatTime(s: number) {
  return `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
}

function AdminLabel() {
  const { id } = useParams<{ id: string }>();
  const meetingId = Number(id);

  const [clusters, setClusters] = useState<Cluster[]>([]);
  const [selected, setSelected] = useState<Cluster | null>(null);
  const [nameInput, setNameInput] = useState("");
  const [knownSpeakers, setKnownSpeakers] = useState<KnownSpeaker[]>([]);
  const [seekTo, setSeekTo] = useState<number | null>(null);
  const [currentTime, setCurrentTime] = useState(0);
  const [error, setError] = useState<string | null>(null);

  function loadClusters() {
    fetch(`/admin/meetings/${meetingId}/clusters`)
      .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
      .then((data: Cluster[]) => {
        setClusters(data);
        setSelected((prev) => {
          const updated = data.find((c) => c.diarization_speaker === prev?.diarization_speaker);
          return updated ?? (data[0] ?? null);
        });
      })
      .catch((e: Error) => setError(e.message));
  }

  function loadSpeakers() {
    fetch("/admin/speakers")
      .then((r) => r.json())
      .then(setKnownSpeakers)
      .catch(() => {});
  }

  useEffect(() => {
    loadClusters();
    loadSpeakers();
  }, [meetingId]);

  useEffect(() => {
    if (selected) setNameInput(selected.speaker_name ?? "");
  }, [selected?.diarization_speaker]);

  function submitLabel() {
    if (!selected || !nameInput.trim()) return;
    fetch(`/admin/meetings/${meetingId}/clusters/${selected.diarization_speaker}/label`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ speaker_name: nameInput.trim() }),
    })
      .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); })
      .then(() => { loadClusters(); loadSpeakers(); })
      .catch((e: Error) => setError(e.message));
  }

  function markCanonical(embeddingId: number) {
    fetch(`/admin/speaker-embeddings/${embeddingId}/canonical`, { method: "POST" })
      .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); })
      .then(loadClusters)
      .catch((e: Error) => setError(e.message));
  }

  if (error) return <p>Error: {error}</p>;

  return (
    <div style={{ display: "flex", gap: "16px" }}>
      {/* Left: cluster list */}
      <div style={{ width: "200px", overflowY: "auto", maxHeight: "700px", flexShrink: 0 }}>
        <h2 style={{ fontSize: "1rem" }}>Clusters</h2>
        {clusters.map((c) => (
          <div
            key={c.diarization_speaker}
            onClick={() => setSelected(c)}
            style={{
              padding: "6px 8px",
              cursor: "pointer",
              background: selected?.diarization_speaker === c.diarization_speaker ? "#e8e8e8" : undefined,
              borderBottom: "1px solid #eee",
            }}
          >
            <div style={{ fontWeight: "bold", fontSize: "0.85rem" }}>{c.diarization_speaker}</div>
            <div style={{ fontSize: "0.8rem", color: c.speaker_name ? "#333" : "#999" }}>
              {c.speaker_name ?? "Unlabeled"}
            </div>
            {c.is_canonical && <div style={{ fontSize: "0.7rem", color: "#888" }}>★ canonical</div>}
          </div>
        ))}
      </div>

      {/* Right: cluster detail */}
      <div style={{ flex: 1 }}>
        {selected && (
          <>
            <div style={{ marginBottom: "8px", display: "flex", gap: "8px", alignItems: "center" }}>
              <input
                list="speaker-names"
                value={nameInput}
                onChange={(e) => setNameInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && submitLabel()}
                placeholder="Speaker name"
                style={{ padding: "4px 8px" }}
              />
              <datalist id="speaker-names">
                {knownSpeakers.map((s) => (
                  <option key={s.id} value={s.speaker_name} />
                ))}
              </datalist>
              <button onClick={submitLabel}>Assign</button>
            </div>

            <VideoPlayer
              videoId={meetingId}
              onTimeUpdate={setCurrentTime}
              seekTo={seekTo}
            />

            <div style={{ overflowY: "auto", maxHeight: "250px", marginTop: "8px" }}>
              <table style={{ tableLayout: "fixed", width: "100%", fontSize: "0.85rem" }}>
                <tbody>
                  {selected.utterances.map((u) => (
                    <tr
                      key={u.id}
                      onClick={() => setSeekTo(u.start)}
                      style={{ cursor: "pointer" }}
                    >
                      <td style={{ width: "45px" }}>{formatTime(u.start)}</td>
                      <td
                        style={{
                          width: "42px",
                          color: u.confidence !== null && u.confidence < 0.7 ? "red" : undefined,
                        }}
                      >
                        {u.confidence !== null ? u.confidence.toFixed(2) : "—"}
                      </td>
                      <td>{u.text}</td>
                      <td style={{ width: "28px" }}>
                        <button
                          title="Mark embedding as canonical"
                          onClick={(e) => {
                            e.stopPropagation();
                            markCanonical(selected.embedding_id);
                          }}
                        >
                          ☆
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

export default AdminLabel;
```

- [ ] **Step 3: Add admin routes to index.tsx**

`webapp/frontend/src/index.tsx` — add the two new imports and two new `<Route>` entries:

```tsx
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Routes, Route } from 'react-router-dom';

import "./styles.css";

import Videos from "./Videos";
import Search from "./Search";
import Navbar from "./Navbar";
import AdminMeetings from "./AdminMeetings";
import AdminLabel from "./AdminLabel";

const root = createRoot(document.getElementById("root")!);
root.render(
  <StrictMode>
    <BrowserRouter>
      <Navbar />
      <Routes>
        <Route path="/" element={<Search />} />
        <Route path="/videos" element={<Videos />} />
        <Route path="/admin/meetings" element={<AdminMeetings />} />
        <Route path="/admin/meetings/:id/label" element={<AdminLabel />} />
      </Routes>
    </BrowserRouter>
  </StrictMode>
);
```

- [ ] **Step 4: Build the frontend**

```bash
cd webapp/frontend && npm run build
```
Expected: build succeeds with no TypeScript errors.

- [ ] **Step 5: Run the app and verify in browser**

```bash
docker compose up webapp --build
```

Navigate to `http://localhost:8000/admin/meetings`. The browser will show a Basic Auth prompt — enter the values of `ADMIN_USER` and `ADMIN_PASSWORD` from your `.env` file.

Verify the following manually:
1. Meetings list loads with names, dates, and unlabeled cluster counts
2. Clicking "Label" navigates to `/admin/meetings/:id/label`
3. Cluster list appears on the left; clicking a cluster populates the right panel
4. Typing in the name input and pressing Enter (or clicking Assign) updates the cluster's label in the left panel
5. The autocomplete datalist suggests existing speaker names as you type
6. Confidence scores below 0.7 appear in red
7. Clicking a row seeks the video to that timestamp
8. Clicking ☆ marks the embedding canonical and shows "★ canonical" on the cluster row in the left panel

- [ ] **Step 6: Commit**

```bash
git add webapp/frontend/src/AdminMeetings.tsx webapp/frontend/src/AdminLabel.tsx webapp/frontend/src/index.tsx
git commit -m "feat: add admin labeling pages for speaker cluster assignment"
```
