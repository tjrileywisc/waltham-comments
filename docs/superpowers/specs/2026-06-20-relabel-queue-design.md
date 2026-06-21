# Relabel Queue Design

**Date:** 2026-06-20  
**Branch:** auto-relabel

## Problem

After transcription runs, some speaker clusters are left unidentified (`speaker_id IS NULL`) because the speaker embedding database didn't yet contain a matching canonical embedding. Today the only way to pick up new identifications (after labeling more meetings or adding canonical embeddings) is to delete the meeting record and re-run full transcription — expensive and slow.

## Goal

Add a "Relabel" button to the admin meetings table that re-runs speaker identification on the unassigned clusters of a single meeting, without touching the transcript or already-assigned clusters.

## Design Decisions

- **Queue mechanism:** DB-backed job table in Postgres. No new infrastructure; fits the existing polling pattern. The webapp inserts a job row; the transcription service picks it up on its next poll cycle.
- **Job processor location:** Extend the existing `while True` loop in `transcription-service/main.py` — jobs are drained after audio file processing, before sleeping. Sequential execution is acceptable because transcription runs weekly and relabeling takes seconds.
- **Cluster filter:** Only `speaker_embeddings` rows where `speaker_id IS NULL AND embedding_vec IS NOT NULL` are relabeled. Any cluster already assigned (manually or automatically) is left untouched.
- **Job status visibility:** The `GET /api/admin/meetings` response includes the most recent `relabel_status` per meeting via a lateral subquery, so the frontend can show pending/running/done without a separate polling endpoint.

## Data Model

### Migration `0009_job_queue.sql`

```sql
CREATE TABLE jobs (
    id           SERIAL PRIMARY KEY,
    job_type     TEXT NOT NULL,
    payload      JSONB NOT NULL DEFAULT '{}',
    status       TEXT NOT NULL DEFAULT 'pending',  -- pending | running | done | failed
    error        TEXT,
    created_at   TIMESTAMP NOT NULL DEFAULT NOW(),
    started_at   TIMESTAMP,
    completed_at TIMESTAMP
);
```

`payload` for a `relabel` job: `{"meeting_id": <int>}`

## Transcription Service

### `db.py` — new functions

- `claim_pending_job(conn) -> tuple[int, str, dict] | None` — atomically claims the oldest pending job using `FOR UPDATE SKIP LOCKED`. Sets `status = 'running'`, `started_at = NOW()`. Returns `(job_id, job_type, payload)` or `None`.
- `complete_job(conn, job_id: int) -> None` — sets `status = 'done'`, `completed_at = NOW()`.
- `fail_job(conn, job_id: int, error: str) -> None` — sets `status = 'failed'`, `error = <message>`, `completed_at = NOW()`.

### New `relabel.py`

Single public function `relabel_meeting(conn, meeting_id: int) -> None`:

1. Query `speaker_embeddings WHERE meeting_id = %s AND speaker_id IS NULL AND embedding_vec IS NOT NULL` — returns `(diarization_speaker, embedding_vec::text)` rows.
2. Build `dict[str, NDArray[np.float64]]` matching the shape `Identifier` expects.
3. Call `Identifier()(conn, speaker_embeddings)` — same call path as during transcription.
4. For each `(cluster_id, (name, confidence))` result:
   - If `name == Identifier.DEFAULT_SPEAKER`: skip (still unidentified).
   - Otherwise: resolve `speaker_id` from `speakers` table, then UPDATE both `utterances` and `speaker_embeddings` for that `(meeting_id, diarization_speaker)`.
5. Commit.

### `main.py` — extended loop

```
while True:
    for each audio/*.wav:
        skip if already processed
        run transcription(meeting_name)
    drain jobs:
        while job := claim_pending_job(conn):
            dispatch by job_type
            complete_job / fail_job
    sleep POLL_INTERVAL
```

## Webapp

### New endpoint

`POST /api/admin/meetings/{meeting_id}/relabel` (admin-protected)

Inserts a `relabel` job into `jobs` and returns `{"ok": True, "job_id": <id>}`.

### Updated `GET /api/admin/meetings`

`get_meetings()` in `webapp/lib/admin.py` gains a lateral subquery:

```sql
LEFT JOIN LATERAL (
    SELECT status FROM jobs
    WHERE job_type = 'relabel'
      AND (payload->>'meeting_id')::int = m.id
    ORDER BY created_at DESC LIMIT 1
) j ON TRUE
```

Adds `relabel_status: "pending" | "running" | "done" | "failed" | null` to each meeting row.

## Frontend (`AdminMeetings.tsx`)

- `Meeting` type gains `relabel_status: string | null`.
- New column in the meetings table with a "Relabel" button per row.
- On click: POST to relabel endpoint, then refresh the meetings list.
- Button is replaced with a status badge while `relabel_status` is `"pending"` or `"running"`.
- On `"failed"`: button is restored with a visual error indicator.
- No automatic polling — user refreshes or navigates away and back.

## Out of Scope

- Retranscription jobs (future job type, queue is designed to support them).
- Bulk "relabel all meetings" — single meeting only.
- Job history/log UI.
