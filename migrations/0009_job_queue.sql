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
