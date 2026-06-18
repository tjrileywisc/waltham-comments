# Speaker Labeling Interface — Design Spec

**Date:** 2026-06-16  
**Branch:** speaker-labeling  
**Status:** Approved

## Overview

An admin-only labeling interface for assigning real names to diarization speaker clusters, replacing the pickle-based speaker embedding store with PostgreSQL, and surfacing per-utterance confidence scores so identification quality is visible and actionable.

---

## Goals

- Let an admin assign names (e.g. "Councilor Smith") to diarization clusters (SPEAKER_0, SPEAKER_1, etc.) for any meeting.
- Store one speaker embedding per diarization cluster per meeting in PostgreSQL (replacing `speaker_db.pkl`).
- Allow the admin to mark a specific utterance as the canonical embedding for a speaker, used for future auto-identification.
- Store a confidence score on every auto-identified utterance so low-confidence identifications are visible.
- No retroactive re-labeling: labeling affects only future meetings.
- Admin access only, via HTTP Basic Auth.

---

## Non-Goals

- Re-running identification on past meetings after a canonical clip is updated.
- Public-facing speaker profiles.
- Automatic embedding accumulation (quality is human-curated, not auto-averaged).

---

## Database Changes

New migration adds two columns to `utterances` and one new table.

```sql
ALTER TABLE utterances ADD COLUMN diarization_speaker TEXT;
ALTER TABLE utterances ADD COLUMN confidence FLOAT;

CREATE TABLE speaker_embeddings (
    id                   SERIAL PRIMARY KEY,
    speaker_id           INT REFERENCES speakers(id),   -- NULL until labeled
    meeting_id           INT REFERENCES meetings(id) NOT NULL,
    diarization_speaker  TEXT NOT NULL,                 -- "SPEAKER_0" etc.
    embedding            vector(256),
    is_canonical         BOOL DEFAULT FALSE,
    created_at           TIMESTAMP DEFAULT NOW(),
    UNIQUE (meeting_id, diarization_speaker)
);
```

**`diarization_speaker`** on utterances preserves the original cluster label from WhisperX so the labeling UI can group utterances by cluster regardless of how identification went. Without it, all DEFAULT utterances from distinct real people are indistinguishable.

**`confidence`** stores the cosine similarity score at identification time. NULL means the speaker was below threshold (assigned DEFAULT) or the meeting predates this feature.

**`speaker_embeddings`** accumulates one row per diarization cluster per meeting. Rows are created at transcription time with `speaker_id = NULL` (unmatched) or the matched speaker's id. Labeling fills in `speaker_id` retroactively. All rows are kept indefinitely; only `is_canonical = TRUE` rows are used for future identification (one per speaker at a time).

---

## Transcription Service Changes

### `identification.py`

- Remove all pickle logic (`DB_PATH`, `save_db`, `load_db`).
- `Identifier.__call__` accepts a `psycopg` connection and queries `speaker_embeddings WHERE is_canonical = TRUE` via pgvector for canonical embeddings.
- Returns `list[tuple[str, float | None]]` — `(speaker_name, confidence)` pairs. Unmatched speakers return `(DEFAULT, None)`.

### `transcription.py`

- Pass a DB connection into `Identifier.__call__`.
- After identification, store `diarization_speaker` and `confidence` on each segment before calling `db.save_meeting`.
- After saving utterances, write one row to `speaker_embeddings` per diarization cluster (matched or not).
- **First-meeting behavior changes**: when no canonical embeddings exist, all cluster embeddings are written with `speaker_id = NULL`, `is_canonical = FALSE`. No auto-seeding. The admin labels the first meeting via the UI.

---

## Backend API

All routes require HTTP Basic Auth. Credentials are read from `ADMIN_USER` and `ADMIN_PASSWORD` environment variables. A single `Depends(get_admin)` FastAPI dependency guards all `/admin/*` routes.

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/admin/meetings` | List all meetings with a count of unlabeled clusters |
| `GET` | `/admin/meetings/{id}/clusters` | All diarization clusters for a meeting, with utterances |
| `POST` | `/admin/meetings/{id}/clusters/{cluster}/label` | Assign a speaker name to a cluster |
| `POST` | `/admin/speaker-embeddings/{embedding_id}/canonical` | Mark an embedding as canonical for its speaker |
| `GET` | `/admin/speakers` | List all named speakers with canonical clip info and confidence stats |

### `GET /admin/meetings/{id}/clusters` response shape

```json
[
  {
    "diarization_speaker": "SPEAKER_0",
    "speaker_name": "Councilor Smith",
    "confidence": 0.84,
    "is_canonical": false,
    "embedding_id": 42,
    "utterances": [
      { "id": 101, "start": 12.4, "end": 15.1, "text": "..." }
    ]
  }
]
```

### `POST /admin/meetings/{id}/clusters/{cluster}/label` behavior

1. Creates a `speakers` row if `speaker_name` doesn't exist yet.
2. Updates all `utterances` in this meeting where `diarization_speaker = cluster` to point to the new `speaker_id`.
3. Sets `speaker_embeddings.speaker_id` for this meeting's cluster row.

### `POST /admin/speaker-embeddings/{embedding_id}/canonical` behavior

No request body. Acts directly on the embedding identified by `embedding_id`.

1. Sets `is_canonical = FALSE` on all other embeddings for the same speaker.
2. Sets `is_canonical = TRUE` on the specified embedding.

### `GET /admin/speakers` response shape

```json
[
  {
    "id": 3,
    "speaker_name": "Councilor Smith",
    "speaker_role": null,
    "canonical_embedding_id": 42,
    "canonical_utterance": { "id": 101, "start": 12.4, "text": "...", "meeting_name": "City Council 1-12-26" },
    "utterance_count": 312,
    "mean_confidence": 0.81,
    "low_confidence_count": 14
  }
]
```

---

## Frontend

Two new pages in the React app. No new npm dependencies.

### `/admin/meetings`

Simple list. Each row shows meeting name, date, and a badge with the count of unlabeled clusters. Clicking a row navigates to the labeling page.

### `/admin/meetings/:id/label`

Split-panel layout:

**Left panel — cluster list**  
One row per diarization cluster. Shows: cluster ID, current speaker name (or "Unlabeled"), confidence score if auto-identified, utterance count. Clicking selects the cluster and populates the right panel.

**Right panel — cluster detail**  
- Speaker name input at the top: text field with autocomplete from existing speaker names. Submitting calls the label endpoint and refreshes the cluster list.
- Utterance list below: timestamp, text, and a star (☆) icon per row. Clicking a row seeks the embedded video to that timestamp. Clicking the star calls the canonical endpoint for this cluster's embedding.
- The embedded `VideoPlayer` component is reused unchanged.

---

## Auth

```python
security = HTTPBasic()

def get_admin(credentials: Annotated[HTTPBasicCredentials, Depends(security)]):
    correct_user = secrets.compare_digest(credentials.username, ADMIN_USER)
    correct_pass = secrets.compare_digest(credentials.password, ADMIN_PASSWORD)
    if not (correct_user and correct_pass):
        raise HTTPException(status_code=401, headers={"WWW-Authenticate": "Basic"})
```

`ADMIN_USER` and `ADMIN_PASSWORD` are read from environment variables at startup. Both must be set or the app refuses to start.

---

## Data Flow Summary

```
New meeting audio
      │
      ▼
WhisperX diarization
  → SPEAKER_0..N + per-cluster embeddings
      │
      ▼
Identifier (reads canonical embeddings from speaker_embeddings table)
  → (speaker_name, confidence) per cluster
  → unmatched → ("DEFAULT", None)
      │
      ▼
save_meeting()
  → utterances rows with diarization_speaker + confidence columns
  → speaker_embeddings rows (one per cluster)
      │
      ▼
Admin opens /admin/meetings/:id/label
  → assigns names to clusters
  → marks a canonical utterance per speaker
      │
      ▼
Next meeting's Identifier reads updated canonical embeddings
```

---

## Open Questions / Future Work

- **Multiple canonical embeddings per speaker**: the current design uses one. A future improvement could allow marking several good clips and using max-similarity or mean pooling.
- **Confidence threshold tuning**: the threshold (currently 0.7) is not exposed in the UI. Could be a future admin setting.
- **Re-identification sweep**: retroactive relabeling of past meetings is explicitly out of scope now but is the natural next feature once canonical embeddings stabilize.
