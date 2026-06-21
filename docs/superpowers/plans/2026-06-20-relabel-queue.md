# Relabel Queue Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Postgres-backed job queue and a "Relabel" button that re-runs speaker identification on a meeting's unassigned clusters without re-transcribing.

**Architecture:** A `jobs` table in Postgres acts as the queue. The webapp inserts a `relabel` job when the button is clicked; the transcription service drains the queue at the end of each poll cycle. The relabel operation loads unassigned `speaker_embeddings` rows (`speaker_id IS NULL`), runs them through the existing `Identifier`, and writes results back to `utterances` and `speaker_embeddings`.

**Tech Stack:** Python 3.13, FastAPI, psycopg3, numpy/sklearn (via `Identifier`), React 19/TypeScript.

## Global Constraints

- Python 3.13 required.
- Use `uv run pytest` (never `pip` or bare `pytest`).
- Logger: `monitoring.setup_logging(name)` only — never `logging.basicConfig()`.
- No new infrastructure (no Redis, Celery, etc.).
- Type annotations and docstrings required on all new functions.
- Run `uv run pytest` after each task; all existing tests must continue to pass.

---

## File Map

| File | Change |
|------|--------|
| `migrations/0009_job_queue.sql` | **Create** — `jobs` table DDL |
| `transcription-service/db.py` | **Modify** — add `claim_pending_job`, `complete_job`, `fail_job` |
| `transcription-service/relabel.py` | **Create** — `relabel_meeting`, `process_pending_jobs` |
| `transcription-service/main.py` | **Modify** — drain jobs after audio scan, before sleep |
| `webapp/lib/admin.py` | **Modify** — add `enqueue_relabel_job`; update `get_meetings` to include `relabel_status` |
| `webapp/main.py` | **Modify** — add `POST /api/admin/meetings/{meeting_id}/relabel` |
| `webapp/frontend/src/AdminMeetings.tsx` | **Modify** — add Relabel button column with status display |
| `tests/test_transcription_db.py` | **Modify** — add job function tests |
| `tests/test_relabel.py` | **Create** — `relabel_meeting` and `process_pending_jobs` tests |
| `tests/test_admin_api.py` | **Modify** — add relabel endpoint test; update meetings test for `relabel_status` |

---

### Task 1: Migration — `jobs` table

**Files:**
- Create: `migrations/0009_job_queue.sql`

**Interfaces:**
- Produces: `jobs` table with columns `id`, `job_type`, `payload` (jsonb), `status`, `error`, `created_at`, `started_at`, `completed_at`. The webapp applies this migration at startup via yoyo-migrations — no manual steps needed once the file exists.

- [ ] **Step 1: Create the migration file**

```sql
-- migrations/0009_job_queue.sql
CREATE TABLE jobs (
    id           SERIAL PRIMARY KEY,
    job_type     TEXT NOT NULL,
    payload      JSONB NOT NULL DEFAULT '{}',
    status       TEXT NOT NULL DEFAULT 'pending',
    error        TEXT,
    created_at   TIMESTAMP NOT NULL DEFAULT NOW(),
    started_at   TIMESTAMP,
    completed_at TIMESTAMP
);
```

- [ ] **Step 2: Verify the file exists and tests still pass**

Run: `uv run pytest`
Expected: all existing tests pass (green).

- [ ] **Step 3: Commit**

```bash
git add migrations/0009_job_queue.sql
git commit -m "feat: add jobs table migration for background job queue"
```

---

### Task 2: Job queue functions in `transcription-service/db.py`

**Files:**
- Modify: `transcription-service/db.py`
- Modify: `tests/test_transcription_db.py`

**Interfaces:**
- Produces:
  - `claim_pending_job(conn) -> tuple[int, str, dict] | None` — atomically claims oldest pending job; returns `(id, job_type, payload)` or `None`.
  - `complete_job(conn, job_id: int) -> None` — marks job `done`.
  - `fail_job(conn, job_id: int, error: str) -> None` — marks job `failed` with error text.

- [ ] **Step 1: Write the failing tests**

In `tests/test_transcription_db.py`, replace the existing import line at the top:

```python
# before
from db import build_window_text, extract_meeting_type, extract_meeting_date, extract_meeting_part, is_meeting_processed, save_meeting
# after
from db import (
    build_window_text, extract_meeting_type, extract_meeting_date,
    extract_meeting_part, is_meeting_processed, save_meeting,
    claim_pending_job, complete_job, fail_job,
)
```

Then add the following tests at the bottom of the file:

```python
def test_claim_pending_job_returns_none_when_queue_empty():
    conn = make_mock_conn(fetchone_results=[None])
    assert claim_pending_job(conn) is None


def test_claim_pending_job_returns_job_tuple():
    conn = make_mock_conn(fetchone_results=[(1, "relabel", {"meeting_id": 5})])
    result = claim_pending_job(conn)
    assert result == (1, "relabel", {"meeting_id": 5})


def test_complete_job_issues_done_update():
    conn = make_mock_conn()
    complete_job(conn, job_id=1)
    sql = conn.cursor.return_value.execute.call_args.args[0]
    assert "done" in sql


def test_fail_job_stores_error_message():
    conn = make_mock_conn()
    fail_job(conn, job_id=1, error="boom")
    params = conn.cursor.return_value.execute.call_args.args[1]
    assert "boom" in params
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_transcription_db.py -k "claim_pending or complete_job or fail_job" -v`
Expected: `ImportError` or `FAILED` — functions don't exist yet.

- [ ] **Step 3: Implement the three functions in `transcription-service/db.py`**

Add after the existing imports, before `build_window_text`:

```python
def claim_pending_job(conn, /) -> tuple[int, str, dict] | None:
    """Atomically claim the oldest pending job.

    Uses FOR UPDATE SKIP LOCKED so concurrent workers never double-claim.
    Returns (job_id, job_type, payload) or None if the queue is empty.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE jobs SET status = 'running', started_at = NOW()
            WHERE id = (
                SELECT id FROM jobs WHERE status = 'pending'
                ORDER BY created_at LIMIT 1 FOR UPDATE SKIP LOCKED
            )
            RETURNING id, job_type, payload
            """
        )
        row = cur.fetchone()
    conn.commit()
    if row is None:
        return None
    return (row[0], row[1], row[2])


def complete_job(conn, job_id: int) -> None:
    """Mark a job as successfully completed."""
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE jobs SET status = 'done', completed_at = NOW() WHERE id = %s",
            (job_id,),
        )
    conn.commit()


def fail_job(conn, job_id: int, error: str) -> None:
    """Mark a job as failed and record the error message."""
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE jobs SET status = 'failed', error = %s, completed_at = NOW() WHERE id = %s",
            (error, job_id),
        )
    conn.commit()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_transcription_db.py -v`
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add transcription-service/db.py tests/test_transcription_db.py
git commit -m "feat: add claim_pending_job, complete_job, fail_job to transcription db"
```

---

### Task 3: `transcription-service/relabel.py`

**Files:**
- Create: `transcription-service/relabel.py`
- Create: `tests/test_relabel.py`

**Interfaces:**
- Consumes: `Identifier` from `transcription-service/identification.py`; `claim_pending_job`, `complete_job`, `fail_job` from `transcription-service/db.py`.
- Produces:
  - `relabel_meeting(conn, meeting_id: int) -> None` — re-runs identification on `speaker_id IS NULL` clusters.
  - `process_pending_jobs(conn) -> None` — drains the job queue; dispatches by `job_type`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_relabel.py`:

```python
import numpy as np
import pytest
from unittest.mock import patch
from helpers import make_mock_conn
from relabel import relabel_meeting, process_pending_jobs


def test_relabel_meeting_does_nothing_when_no_unassigned_clusters():
    """When all clusters are already assigned, no UPDATEs should run."""
    conn = make_mock_conn(fetchall_results=[[]])  # empty SELECT
    relabel_meeting(conn, meeting_id=1)
    sqls = [call.args[0] for call in conn.cursor.return_value.execute.call_args_list]
    assert not any("UPDATE" in sql for sql in sqls)


def test_relabel_meeting_skips_clusters_that_stay_default():
    """Clusters that Identifier still can't match are left alone (no UPDATE)."""
    conn = make_mock_conn(
        fetchall_results=[
            [("SPEAKER_0", "[0.0,1.0]")],  # relabel SELECT: one unassigned cluster
            [],                              # Identifier's SELECT: no known speakers in DB
        ],
    )
    relabel_meeting(conn, meeting_id=1)
    sqls = [call.args[0] for call in conn.cursor.return_value.execute.call_args_list]
    assert not any("UPDATE" in sql for sql in sqls)


def test_relabel_meeting_updates_matched_clusters():
    """Clusters matched above threshold get utterances and speaker_embeddings updated."""
    conn = make_mock_conn(
        fetchall_results=[
            [("SPEAKER_0", "[1.0,0.0]")],       # relabel SELECT
            [("Alice", "[1.0,0.0]")],             # Identifier's SELECT
        ],
        fetchone_results=[(7,)],                  # SELECT id FROM speakers WHERE speaker_name = 'Alice'
    )
    relabel_meeting(conn, meeting_id=3)
    sqls = [call.args[0] for call in conn.cursor.return_value.execute.call_args_list]
    update_sqls = [s for s in sqls if "UPDATE" in s]
    assert len(update_sqls) == 2  # utterances + speaker_embeddings


def test_relabel_meeting_skips_update_when_speaker_not_found():
    """If Identifier returns a name not in speakers table, skip rather than crash."""
    conn = make_mock_conn(
        fetchall_results=[
            [("SPEAKER_0", "[1.0,0.0]")],
            [("Alice", "[1.0,0.0]")],
        ],
        fetchone_results=[None],  # speaker not in DB
    )
    relabel_meeting(conn, meeting_id=3)
    sqls = [call.args[0] for call in conn.cursor.return_value.execute.call_args_list]
    assert not any("UPDATE" in sql for sql in sqls)


def test_process_pending_jobs_dispatches_relabel():
    """process_pending_jobs calls relabel_meeting with the payload meeting_id."""
    conn = make_mock_conn()
    with patch("relabel.claim_pending_job", side_effect=[(1, "relabel", {"meeting_id": 5}), None]), \
         patch("relabel.relabel_meeting") as mock_relabel, \
         patch("relabel.complete_job") as mock_complete:
        process_pending_jobs(conn)
    mock_relabel.assert_called_once_with(conn, 5)
    mock_complete.assert_called_once_with(conn, 1)


def test_process_pending_jobs_calls_fail_job_on_error():
    """When relabel_meeting raises, the job is marked failed with the error message."""
    conn = make_mock_conn()
    with patch("relabel.claim_pending_job", side_effect=[(1, "relabel", {"meeting_id": 5}), None]), \
         patch("relabel.relabel_meeting", side_effect=Exception("disk full")), \
         patch("relabel.fail_job") as mock_fail:
        process_pending_jobs(conn)
    mock_fail.assert_called_once_with(conn, 1, "disk full")


def test_process_pending_jobs_stops_when_queue_empty():
    """process_pending_jobs stops looping as soon as claim returns None."""
    conn = make_mock_conn()
    with patch("relabel.claim_pending_job", return_value=None) as mock_claim:
        process_pending_jobs(conn)
    mock_claim.assert_called_once()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_relabel.py -v`
Expected: `ModuleNotFoundError: No module named 'relabel'`.

- [ ] **Step 3: Implement `transcription-service/relabel.py`**

```python
import numpy as np
from numpy.typing import NDArray

from db import claim_pending_job, complete_job, fail_job
from identification import Identifier
from monitoring import setup_logging

logger = setup_logging("transcription")


def relabel_meeting(conn, meeting_id: int) -> None:
    """Re-run speaker identification on all unassigned clusters for a meeting.

    Only touches speaker_embeddings rows where speaker_id IS NULL.
    Clusters already assigned (manually or automatically) are left untouched.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT diarization_speaker, embedding_vec::text
            FROM speaker_embeddings
            WHERE meeting_id = %s AND speaker_id IS NULL AND embedding_vec IS NOT NULL
            """,
            (meeting_id,),
        )
        rows = cur.fetchall()

    if not rows:
        logger.info(f"No unassigned clusters for meeting {meeting_id}, skipping relabel")
        return

    speaker_embeddings: dict[str, NDArray[np.float64]] = {
        disp: np.array([float(x) for x in vec_text.strip("[]").split(",")], dtype=np.float64)
        for disp, vec_text in rows
    }

    results = Identifier()(conn, speaker_embeddings)
    cluster_ids = list(speaker_embeddings.keys())

    with conn.cursor() as cur:
        for cluster_id, (name, confidence) in zip(cluster_ids, results):
            if name == Identifier.DEFAULT_SPEAKER:
                continue

            cur.execute("SELECT id FROM speakers WHERE speaker_name = %s", (name,))
            row = cur.fetchone()
            if row is None:
                logger.warning(f"Speaker '{name}' returned by Identifier but not found in speakers table")
                continue
            speaker_id = row[0]

            cur.execute(
                "UPDATE utterances SET speaker_id = %s, confidence = %s "
                "WHERE meeting_id = %s AND diarization_speaker = %s",
                (speaker_id, confidence, meeting_id, cluster_id),
            )
            cur.execute(
                "UPDATE speaker_embeddings SET speaker_id = %s "
                "WHERE meeting_id = %s AND diarization_speaker = %s",
                (speaker_id, meeting_id, cluster_id),
            )
    conn.commit()
    logger.info(f"Relabel complete for meeting {meeting_id}")


def process_pending_jobs(conn) -> None:
    """Drain all pending jobs from the queue, processing each in order."""
    while True:
        job = claim_pending_job(conn)
        if job is None:
            break
        job_id, job_type, payload = job
        logger.info(f"Processing job {job_id} (type={job_type})")
        try:
            if job_type == "relabel":
                relabel_meeting(conn, payload["meeting_id"])
            else:
                raise ValueError(f"Unknown job type: {job_type!r}")
            complete_job(conn, job_id)
            logger.info(f"Job {job_id} completed")
        except Exception as e:
            logger.error(f"Job {job_id} failed: {e}")
            fail_job(conn, job_id, str(e))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_relabel.py -v`
Expected: all 7 tests pass.

- [ ] **Step 5: Run full suite**

Run: `uv run pytest`
Expected: all existing tests still pass.

- [ ] **Step 6: Commit**

```bash
git add transcription-service/relabel.py tests/test_relabel.py
git commit -m "feat: add relabel_meeting and process_pending_jobs"
```

---

### Task 4: Extend `transcription-service/main.py`

**Files:**
- Modify: `transcription-service/main.py`

**Interfaces:**
- Consumes: `process_pending_jobs` from `transcription-service/relabel.py`; `claim_pending_job` etc. already tested in Task 2–3.

- [ ] **Step 1: Replace `transcription-service/main.py` with the updated version**

```python
import glob
import psycopg
import os
import time

from db import is_meeting_processed
from relabel import process_pending_jobs
from transcription import transcription
from monitoring import setup_logging

logger = setup_logging("transcription")

POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL_SECONDS", 3600))


def main():
    """Poll for audio files to transcribe and drain the job queue each cycle."""
    while True:
        logger.info("Checking for audio files to transcribe...")
        for audio_file in glob.glob("audio/*.wav"):
            meeting_name = os.path.basename(audio_file).replace(".wav", "")
            with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
                if is_meeting_processed(conn, meeting_name):
                    continue

            logger.info(f"Transcribing {meeting_name}...")
            transcription(meeting_name)

        logger.info("Checking job queue...")
        with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
            process_pending_jobs(conn)

        logger.info(f"Done. Sleeping {POLL_INTERVAL}s.")
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run full test suite**

Run: `uv run pytest`
Expected: all tests pass.

- [ ] **Step 3: Commit**

```bash
git add transcription-service/main.py
git commit -m "feat: drain job queue after each transcription poll cycle"
```

---

### Task 5: Webapp — `enqueue_relabel_job` + new endpoint

**Files:**
- Modify: `webapp/lib/admin.py`
- Modify: `webapp/main.py`
- Modify: `tests/test_admin_api.py`

**Interfaces:**
- Produces:
  - `enqueue_relabel_job(conn, meeting_id: int) -> int` in `webapp/lib/admin.py` — inserts job, returns `job_id`.
  - `POST /api/admin/meetings/{meeting_id}/relabel` — returns `{"ok": True, "job_id": <int>}`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_admin_api.py`:

```python
def test_admin_relabel_requires_auth():
    r = client.post("/api/admin/meetings/5/relabel")
    assert r.status_code == 401


def test_admin_relabel_enqueues_job():
    mock_conn = make_mock_conn(fetchone_results=[(99,)])  # RETURNING id
    with patch("main.connect", return_value=mock_conn):
        r = client.post("/api/admin/meetings/5/relabel", auth=AUTH)
    assert r.status_code == 200
    assert r.json() == {"ok": True, "job_id": 99}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_admin_api.py -k "relabel" -v`
Expected: `FAILED` — endpoint doesn't exist yet (404).

- [ ] **Step 3: Add `enqueue_relabel_job` to `webapp/lib/admin.py`**

Add after the existing imports (add `import json` at the top of the file):

```python
import json
```

Add the new function at the bottom of `webapp/lib/admin.py`:

```python
def enqueue_relabel_job(conn, meeting_id: int) -> int:
    """Insert a relabel job into the queue and return its id."""
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO jobs (job_type, payload) VALUES ('relabel', %s) RETURNING id",
            (json.dumps({"meeting_id": meeting_id}),),
        )
        job_id = cur.fetchone()[0]
    conn.commit()
    return job_id
```

- [ ] **Step 4: Add the endpoint to `webapp/main.py`**

Update the import line at the top of `webapp/main.py`:

```python
from lib.admin import (
    get_admin, get_meetings, get_clusters,
    label_cluster, set_canonical, get_speakers, enqueue_relabel_job,
)
```

Add the new endpoint after `admin_speakers`:

```python
@app.post("/api/admin/meetings/{meeting_id}/relabel")
def admin_relabel_meeting(meeting_id: int, _=Depends(get_admin)):
    """Enqueue a relabel job for a single meeting."""
    with connect() as conn:
        job_id = enqueue_relabel_job(conn, meeting_id)
    return {"ok": True, "job_id": job_id}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_admin_api.py -v`
Expected: all tests pass.

- [ ] **Step 6: Run full suite**

Run: `uv run pytest`
Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add webapp/lib/admin.py webapp/main.py tests/test_admin_api.py
git commit -m "feat: add POST /api/admin/meetings/{id}/relabel endpoint"
```

---

### Task 6: Webapp — `get_meetings` with `relabel_status`

**Files:**
- Modify: `webapp/lib/admin.py`
- Modify: `tests/test_admin_api.py`

**Interfaces:**
- Produces: `get_meetings` returns dicts with a new `relabel_status: str | None` key (values: `"pending"`, `"running"`, `"done"`, `"failed"`, or `None`).

- [ ] **Step 1: Update the existing meetings test and add a new one**

In `tests/test_admin_api.py`, find `test_admin_meetings_returns_list` and update the mock data to include a 6th column:

```python
def test_admin_meetings_returns_list():
    mock_conn = make_mock_conn(
        fetchall_results=[[(1, "City Council 1-12-26", "2026-01-12", "City Council", 2, None)]]
    )
    with patch("main.connect", return_value=mock_conn):
        r = client.get("/api/admin/meetings", auth=AUTH)
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["meeting_name"] == "City Council 1-12-26"
    assert data[0]["unlabeled_count"] == 2
    assert data[0]["relabel_status"] is None
```

Add a new test:

```python
def test_admin_meetings_includes_relabel_status():
    mock_conn = make_mock_conn(
        fetchall_results=[[(1, "City Council 1-12-26", "2026-01-12", "City Council", 0, "pending")]]
    )
    with patch("main.connect", return_value=mock_conn):
        r = client.get("/api/admin/meetings", auth=AUTH)
    assert r.status_code == 200
    assert r.json()[0]["relabel_status"] == "pending"
```

- [ ] **Step 2: Run tests to verify the updated test fails**

Run: `uv run pytest tests/test_admin_api.py::test_admin_meetings_returns_list -v`
Expected: `FAILED` — `KeyError: 'relabel_status'` or index error.

- [ ] **Step 3: Update `get_meetings` in `webapp/lib/admin.py`**

Replace the existing `get_meetings` function:

```python
def get_meetings(conn) -> list[dict]:
    """Return all meetings with their unlabeled cluster count and latest relabel job status."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT m.id, m.meeting_name, m.meeting_date, m.meeting_type,
                   COUNT(se.id) FILTER (WHERE se.speaker_id IS NULL) AS unlabeled_count,
                   j.status AS relabel_status
            FROM meetings m
            LEFT JOIN speaker_embeddings se ON se.meeting_id = m.id
            LEFT JOIN LATERAL (
                SELECT status FROM jobs
                WHERE job_type = 'relabel'
                  AND (payload->>'meeting_id')::int = m.id
                ORDER BY created_at DESC LIMIT 1
            ) j ON TRUE
            GROUP BY m.id, j.status
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
            "relabel_status": r[5],
        }
        for r in rows
    ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_admin_api.py -v`
Expected: all tests pass.

- [ ] **Step 5: Run full suite**

Run: `uv run pytest`
Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add webapp/lib/admin.py tests/test_admin_api.py
git commit -m "feat: include relabel_status in GET /api/admin/meetings response"
```

---

### Task 7: Frontend — Relabel button

**Files:**
- Modify: `webapp/frontend/src/AdminMeetings.tsx`

**Interfaces:**
- Consumes: `relabel_status` field on `Meeting` objects (Task 6); `POST /api/admin/meetings/{id}/relabel` (Task 5).

- [ ] **Step 1: Update `AdminMeetings.tsx`**

Replace the entire file contents:

```tsx
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

type Meeting = {
  id: number;
  meeting_name: string;
  meeting_date: string;
  meeting_type: string;
  unlabeled_count: number;
  video_id: number | null;
  relabel_status: "pending" | "running" | "done" | "failed" | null;
};

type SortKey = "meeting_date" | "meeting_name" | "meeting_type" | "unlabeled_count";
type SortDir = "asc" | "desc";

/**
 * Meeting level view of currently unlabeled speakers in meetings
 */
function AdminMeetings() {
  const [meetings, setMeetings] = useState<Meeting[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [sortKey, setSortKey] = useState<SortKey>("meeting_date");
  const [sortDir, setSortDir] = useState<SortDir>("asc");

  function loadMeetings() {
    fetch("/api/admin/meetings")
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then(setMeetings)
      .catch((e: Error) => setError(e.message));
  }

  useEffect(() => {
    loadMeetings();
  }, []);

  function handleSort(key: SortKey) {
    if (key === sortKey) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("asc");
    }
  }

  function handleRelabel(meetingId: number) {
    fetch(`/api/admin/meetings/${meetingId}/relabel`, { method: "POST" })
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
      })
      .then(loadMeetings)
      .catch((e: Error) => setError(e.message));
  }

  const sorted = [...meetings].sort((a, b) => {
    const av = a[sortKey];
    const bv = b[sortKey];
    const cmp = av < bv ? -1 : av > bv ? 1 : 0;
    return sortDir === "asc" ? cmp : -cmp;
  });

  function SortIndicator({ col }: { col: SortKey }) {
    if (col !== sortKey) return null;
    return <span>{sortDir === "asc" ? " ↑" : " ↓"}</span>;
  }

  if (error) return <p>Error: {error}</p>;

  return (
    <div>
      <h1>Speaker Labeling</h1>
      <table>
        <thead>
          <tr>
            <th style={{ cursor: "pointer" }} onClick={() => handleSort("meeting_date")}>
              Date<SortIndicator col="meeting_date" />
            </th>
            <th style={{ cursor: "pointer" }} onClick={() => handleSort("meeting_name")}>
              Name<SortIndicator col="meeting_name" />
            </th>
            <th style={{ cursor: "pointer" }} onClick={() => handleSort("meeting_type")}>
              Type<SortIndicator col="meeting_type" />
            </th>
            <th style={{ cursor: "pointer" }} onClick={() => handleSort("unlabeled_count")}>
              Unlabeled clusters<SortIndicator col="unlabeled_count" />
            </th>
            <th></th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((m) => (
            <tr key={m.id}>
              <td>{m.meeting_date}</td>
              <td>{m.meeting_name}</td>
              <td>{m.meeting_type}</td>
              <td>{m.unlabeled_count > 0 ? m.unlabeled_count : "—"}</td>
              <td>
                <Link to={`/admin/meetings/${m.id}/label`}>Label</Link>
              </td>
              <td>
                {m.relabel_status === "pending" || m.relabel_status === "running" ? (
                  <span style={{ color: "#888" }}>
                    {m.relabel_status === "pending" ? "⏳ Pending" : "⚙ Running"}
                  </span>
                ) : (
                  <button
                    onClick={() => handleRelabel(m.id)}
                    style={m.relabel_status === "failed" ? { color: "red" } : undefined}
                  >
                    {m.relabel_status === "failed" ? "Relabel (failed)" : "Relabel"}
                  </button>
                )}
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

- [ ] **Step 2: Build the frontend**

```bash
cd webapp/frontend && npm run build
```
Expected: build succeeds with no TypeScript errors.

- [ ] **Step 3: Run full test suite**

```bash
cd ../.. && uv run pytest
```
Expected: all tests pass.

- [ ] **Step 4: Commit**

```bash
git add webapp/frontend/src/AdminMeetings.tsx webapp/frontend/dist
git commit -m "feat: add Relabel button to admin meetings table"
```
